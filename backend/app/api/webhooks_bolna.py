"""Bolna Custom Function and call-lifecycle webhooks.

Bolna points each custom tool at a dedicated URL. We expose:

  POST /webhooks/bolna/tools/{tool_name}
  POST /webhooks/bolna/tools          (optional; body must include tool/name)
  POST /webhooks/bolna/call-status   (agent webhook_url for execution updates)

The adapter normalizes Bolna's body into the shared RetellToolDispatcher
so scheduling services stay provider-agnostic.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.bolna.schemas import (
    BolnaExecutionWebhook,
    normalize_bolna_invocation,
)
from app.adapters.bolna.security import verify_bolna_bearer
from app.adapters.retell.dispatcher import RetellToolDispatcher
from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.deps import get_db
from app.repositories.call_repository import CallRepository

router = APIRouter(prefix="/webhooks/bolna", tags=["bolna"])
logger = get_logger(__name__)

_COMPLETED_STATUSES = frozenset(
    {
        "completed",
        "complete",
        "failed",
        "busy",
        "no-answer",
        "canceled",
        "cancelled",
        "stopped",
    }
)


async def _enforce_auth(request: Request, settings: Settings) -> bytes:
    raw_body = await request.body()
    if settings.bolna_api_token and settings.bolna_verify_auth:
        verify_bolna_bearer(
            authorization_header=request.headers.get("Authorization"),
            api_token=settings.bolna_api_token,
        )
    elif settings.is_production and settings.bolna_verify_auth:
        raise ValidationError(
            "BOLNA_API_TOKEN must be configured in production for Bolna webhook auth."
        )
    return raw_body


@router.post(
    "/tools/{tool_name}",
    summary="Bolna Custom Function entrypoint (per-tool URL)",
)
async def invoke_bolna_tool(
    tool_name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    raw_body = await _enforce_auth(request, settings)
    body = json.loads(raw_body.decode("utf-8") or "{}")
    if not isinstance(body, dict):
        raise ValidationError("Bolna tool body must be a JSON object.")

    invocation = normalize_bolna_invocation(tool_name, body)
    dispatcher = RetellToolDispatcher(db)
    result = await dispatcher.dispatch(invocation)
    return JSONResponse(content=result)


@router.post(
    "/tools",
    summary="Bolna Custom Function entrypoint (single URL; body must include tool name)",
)
async def invoke_bolna_tool_shared(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    raw_body = await _enforce_auth(request, settings)
    body = json.loads(raw_body.decode("utf-8") or "{}")
    if not isinstance(body, dict):
        raise ValidationError("Bolna tool body must be a JSON object.")

    tool_name = str(body.get("tool") or body.get("name") or "").strip()
    if not tool_name:
        raise ValidationError(
            "Body must include 'tool' or 'name', or use /webhooks/bolna/tools/{tool_name}."
        )

    invocation = normalize_bolna_invocation(tool_name, body)
    dispatcher = RetellToolDispatcher(db)
    result = await dispatcher.dispatch(invocation)
    return JSONResponse(content=result)


@router.post(
    "/call-status",
    summary="Bolna agent webhook_url — mark Call rows completed on terminal statuses",
)
async def bolna_call_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    raw_body = await _enforce_auth(request, settings)
    body = json.loads(raw_body.decode("utf-8") or "{}")
    if not isinstance(body, dict):
        raise ValidationError("Bolna call-status body must be a JSON object.")

    payload = BolnaExecutionWebhook.model_validate(body)
    status = (payload.status or "").strip().lower()
    external_id = payload.external_call_id()

    if not external_id:
        logger.info("bolna_call_status_ignored", reason="missing_execution_id")
        return {"ok": True, "updated": False}

    if status and status not in _COMPLETED_STATUSES:
        logger.info(
            "bolna_call_status_ignored",
            reason="non_terminal_status",
            status=status,
            bolna_call_id=external_id,
        )
        return {"ok": True, "updated": False, "status": status}

    async with db.begin():
        call = await CallRepository(db).mark_completed(external_id)
    return {
        "ok": True,
        "updated": call is not None,
        "call_id": str(call.id) if call else None,
        "status": status or None,
    }
