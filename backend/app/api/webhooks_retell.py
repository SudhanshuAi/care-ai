"""Retell custom-function and call-lifecycle webhooks.

These routes sit *beside* the `/tools` REST API. Retell never needs to
speak our internal `/tools` contracts directly; it posts
`{name, args, call}` here, and the adapter delegates to the same
services the REST layer uses.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.retell.dispatcher import RetellToolDispatcher
from app.adapters.retell.schemas import RetellCallContext, RetellToolInvocation
from app.adapters.retell.security import verify_retell_signature
from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.core.observability import (
    CALL_ID_HEADER,
    CONVERSATION_ID_HEADER,
    PROVIDER_RETELL,
    bind_conversation_context,
    resolve_conversation_id,
)
from app.deps import get_db
from app.repositories.call_repository import CallRepository
from app.schemas.conversation import ConversationStateResponse
from app.services.conversation_state_service import ConversationStateService

router = APIRouter(prefix="/webhooks/retell", tags=["retell"])
logger = get_logger(__name__)


async def _enforce_signature(request: Request, settings: Settings) -> bytes:
    raw_body = await request.body()
    if settings.retell_api_key and settings.retell_verify_signatures:
        verify_retell_signature(
            raw_body=raw_body,
            signature_header=request.headers.get("X-Retell-Signature"),
            api_key=settings.retell_api_key,
        )
    elif settings.is_production:
        raise ValidationError(
            "RETELL_API_KEY must be configured in production for signature verification."
        )
    return raw_body


def _correlation_headers() -> dict[str, str]:
    ctx = structlog.contextvars.get_contextvars()
    headers: dict[str, str] = {}
    if ctx.get("call_id"):
        headers[CALL_ID_HEADER] = str(ctx["call_id"])
    if ctx.get("conversation_id"):
        headers[CONVERSATION_ID_HEADER] = str(ctx["conversation_id"])
    return headers


@router.post(
    "/tools",
    summary="Retell Custom Function entrypoint for all voice tools",
)
async def invoke_retell_tool(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    raw_body = await _enforce_signature(request, settings)
    payload = RetellToolInvocation.model_validate_json(raw_body)
    dispatcher = RetellToolDispatcher(db)
    result = await dispatcher.dispatch(payload)
    # Retell feeds this JSON body back into the LLM as the tool result.
    return JSONResponse(content=result, headers=_correlation_headers())


@router.post(
    "/call-ended",
    summary="Mark a Call row completed when Retell ends the session",
)
async def retell_call_ended(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    raw_body = await _enforce_signature(request, settings)
    body = json.loads(raw_body.decode("utf-8") or "{}")
    # Retell event envelopes vary slightly by webhook mode; accept both
    # flat call objects and `{event, call}` wrappers.
    call_obj = body.get("call") if isinstance(body, dict) else None
    if call_obj is None and isinstance(body, dict):
        call_obj = body
    retell_call_id = None
    if isinstance(call_obj, dict):
        retell_call_id = call_obj.get("call_id")

    if not retell_call_id:
        logger.info(
            "retell_call_ended_ignored",
            reason="missing_call_id",
            provider=PROVIDER_RETELL,
            status="ignored",
        )
        return {"ok": True, "updated": False}

    state_service = ConversationStateService(db, CallRepository(db))
    calls = CallRepository(db)
    # A call that never reached a function still has a terminal Retell
    # webhook. Create its memory row here so every Retell call is
    # durable, not only calls that invoked a scheduling tool.
    conversation = await state_service.restore_or_create(
        RetellCallContext.model_validate(call_obj)
    )
    conversation_id = await resolve_conversation_id(
        call=conversation, lookup=calls.by_id
    )
    # Lookups during correlation may autobegin; clear before complete().
    if db.in_transaction():
        await db.commit()
    bind_conversation_context(
        provider=PROVIDER_RETELL,
        call_id=str(retell_call_id),
        conversation_id=conversation_id,
        database_call_id=str(conversation.id) if conversation else None,
        language=(
            conversation.language
            if conversation and conversation.language
            else (call_obj.get("language") if isinstance(call_obj, dict) else None)
        ),
        conversation_state=None,
    )

    status_value = str(
        call_obj.get("call_status")
        or call_obj.get("status")
        or body.get("event")
        or ""
    ).lower()
    disconnected = any(
        marker in status_value
        for marker in ("disconnect", "dropped", "error", "failed")
    )
    state = await state_service.complete(
        retell_call_id=str(retell_call_id), disconnected=disconnected
    )
    logger.info(
        "retell_call_ended",
        call_id=str(retell_call_id),
        conversation_id=conversation_id,
        provider=PROVIDER_RETELL,
        status="disconnected" if disconnected else "completed",
        updated=state is not None,
    )
    return {
        "ok": True,
        "updated": state is not None,
        "call_id": state.database_call_id if state else None,
        "conversation_summary": state.conversation_summary if state else None,
        "disconnected": disconnected,
    }


@router.get(
    "/call-context/{call_id}",
    response_model=ConversationStateResponse,
    summary="Retrieve durable conversation memory for a Retell call",
)
async def retell_call_context(
    call_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationStateResponse:
    """Read-only operational endpoint used to inspect/restore call state."""

    return await ConversationStateService(db, CallRepository(db)).get_state(call_id)
