"""Conversation-scoped observability helpers for structured logs.

HTTP middleware already binds ``request_id``. Voice adapters bind the
fields below so every nested log line (and metrics row) can be filtered
by call, patient, tool, and conversation across reconnects.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from app.db.models.call import Call

PROVIDER_RETELL = "retell"
PROVIDER_BOLNA = "bolna"
PROVIDER_REST = "rest"

# Response / inbound headers for cross-service correlation.
CALL_ID_HEADER = "X-Call-ID"
CONVERSATION_ID_HEADER = "X-Conversation-ID"


def bind_request_provider(path: str) -> str:
    """Infer telephony/API provider from the request path and bind it."""

    if path.startswith("/webhooks/retell"):
        provider = PROVIDER_RETELL
    elif path.startswith("/webhooks/bolna"):
        provider = PROVIDER_BOLNA
    else:
        provider = PROVIDER_REST
    structlog.contextvars.bind_contextvars(provider=provider)
    return provider


def conversation_state_snapshot(call: Call | None) -> dict[str, Any] | None:
    """Compact, log-safe view of durable call memory."""

    if call is None:
        return None
    return {
        "current_intent": call.current_intent,
        "last_tool_called": call.last_tool_called,
        "has_pending_confirmation": call.pending_confirmation is not None,
        "has_availability_search": call.last_availability_search is not None,
        "call_status": call.status.value if call.status is not None else None,
    }


def bind_conversation_context(
    *,
    provider: str,
    tool_name: str | None = None,
    call_id: str | None = None,
    conversation_id: str | None = None,
    database_call_id: str | None = None,
    patient_id: str | None = None,
    appointment_id: str | None = None,
    language: str | None = None,
    conversation_state: dict[str, Any] | None = None,
) -> None:
    """Bind standard voice/tool fields into structlog contextvars.

    ``None`` values are omitted so logs stay sparse. Pass explicit
    ``None`` via ``clear=`` only when intentionally wiping a field;
    this helper never clears unrelated context (e.g. ``request_id``).
    """

    payload: dict[str, Any] = {"provider": provider}
    if tool_name is not None:
        payload["tool_name"] = tool_name
    if call_id is not None:
        payload["call_id"] = call_id
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    if database_call_id is not None:
        payload["database_call_id"] = database_call_id
    if patient_id is not None:
        payload["patient_id"] = patient_id
    if appointment_id is not None:
        payload["appointment_id"] = appointment_id
    if language is not None:
        payload["language"] = language
    if conversation_state is not None:
        payload["conversation_state"] = conversation_state
    structlog.contextvars.bind_contextvars(**payload)


def patient_id_from_call(call: Call | None) -> str | None:
    if call is None:
        return None
    value = call.identified_patient_id or call.patient_id
    return str(value) if value is not None else None


def extract_appointment_id(
    args: dict[str, Any] | None,
    result: dict[str, Any] | None = None,
) -> str | None:
    """Pull appointment_id from tool args or a successful tool result."""

    for source in (result, args):
        if not source:
            continue
        value = source.get("appointment_id")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def extract_patient_id(
    args: dict[str, Any] | None,
    result: dict[str, Any] | None = None,
    *,
    fallback: str | None = None,
) -> str | None:
    if args:
        value = args.get("patient_id")
        if value is not None and str(value).strip():
            return str(value).strip()
    if result:
        value = result.get("patient_id")
        if value is not None and str(value).strip():
            return str(value).strip()
        patients = result.get("patients")
        if (
            isinstance(patients, list)
            and len(patients) == 1
            and isinstance(patients[0], dict)
            and patients[0].get("id") is not None
            and not result.get("requires_disambiguation")
        ):
            return str(patients[0]["id"])
    return fallback


async def resolve_conversation_id(
    *,
    call: Call | None,
    lookup,
) -> str | None:
    """Stable id spanning reconnects: root Call UUID in the resume chain.

    ``lookup`` is an async callable ``UUID -> Call | None`` (typically
    ``CallRepository.by_id``).
    """

    if call is None:
        return None
    current = call
    seen: set[UUID] = set()
    while current.resumed_from_call_id is not None and current.id not in seen:
        seen.add(current.id)
        parent = await lookup(current.resumed_from_call_id)
        if parent is None:
            return str(current.resumed_from_call_id)
        current = parent
    return str(current.id)


def current_request_id() -> str | None:
    context = structlog.contextvars.get_contextvars()
    value = context.get("request_id")
    return str(value) if value is not None else None


def correlation_response_headers() -> dict[str, str]:
    """Return known voice correlation IDs as safe response headers."""

    context = structlog.contextvars.get_contextvars()
    headers: dict[str, str] = {}
    if context.get("call_id"):
        headers[CALL_ID_HEADER] = str(context["call_id"])
    if context.get("conversation_id"):
        headers[CONVERSATION_ID_HEADER] = str(context["conversation_id"])
    return headers
