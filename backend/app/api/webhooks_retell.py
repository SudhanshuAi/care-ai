"""Retell custom-function and call-lifecycle webhooks.

These routes sit *beside* the `/tools` REST API. Retell never needs to
speak our internal `/tools` contracts directly; it posts
`{name, args, call}` here, and the adapter delegates to the same
services the REST layer uses.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.retell.dispatcher import RetellToolDispatcher
from app.adapters.retell.schemas import RetellToolInvocation
from app.adapters.retell.security import verify_retell_signature
from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.deps import get_db
from app.repositories.call_repository import CallRepository

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
    return JSONResponse(content=result)


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
        logger.info("retell_call_ended_ignored", reason="missing_call_id")
        return {"ok": True, "updated": False}

    async with db.begin():
        call = await CallRepository(db).mark_completed(str(retell_call_id))
    return {
        "ok": True,
        "updated": call is not None,
        "call_id": str(call.id) if call else None,
    }
