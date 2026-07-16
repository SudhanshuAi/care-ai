"""Bolna request shapes and normalization into the shared tool dispatcher."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.retell.schemas import RetellCallContext, RetellToolInvocation

# Fields Bolna (or our tool schemas) may send as call metadata rather than
# tool business arguments. Stripped from `args` and mapped onto call context.
_META_KEYS = frozenset(
    {
        "tool",
        "name",
        "execution_id",
        "call_sid",
        "from_number",
        "to_number",
        "call_type",
        "direction",
        "agent_id",
        "telephony_data",
    }
)


def _coerce_arg(key: str, value: Any) -> Any:
    """Bolna `%(param)s` substitution always yields strings."""

    if key == "earliest_only" and isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if key == "limit" and isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return value


class BolnaToolBody(BaseModel):
    """Loose body Bolna POSTs for a custom function.

    Bolna substitutes `%(param)s` values into the `param` object and sends
    that object as JSON. We accept extra keys (context variables) so the
    dashboard can inject `{from_number}` / `{call_sid}` without schema churn.
    """

    model_config = ConfigDict(extra="allow")

    phone: str | None = None
    full_name: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    call_sid: str | None = None
    execution_id: str | None = None
    call_type: str | None = None
    direction: str | None = None
    agent_id: str | None = None


def normalize_bolna_invocation(
    tool_name: str, body: dict[str, Any] | None
) -> RetellToolInvocation:
    """Map a Bolna custom-function POST into the shared dispatcher contract."""

    payload = dict(body or {})
    telephony = payload.get("telephony_data")
    if isinstance(telephony, dict):
        payload.setdefault("from_number", telephony.get("from_number"))
        payload.setdefault("to_number", telephony.get("to_number"))
        payload.setdefault("call_type", telephony.get("call_type"))
        payload.setdefault(
            "call_sid",
            telephony.get("provider_call_id") or telephony.get("call_sid"),
        )

    call_id = payload.get("call_sid") or payload.get("execution_id")
    if call_id is not None:
        call_id = f"bolna:{call_id}"

    from_number = (
        payload.get("from_number")
        or payload.get("phone")
        or (telephony.get("from_number") if isinstance(telephony, dict) else None)
    )
    to_number = payload.get("to_number")
    direction = payload.get("call_type") or payload.get("direction")

    args = {
        key: _coerce_arg(key, value)
        for key, value in payload.items()
        if key not in _META_KEYS and value is not None and value != ""
    }

    call: RetellCallContext | None = None
    if call_id or from_number or to_number or direction or payload.get("agent_id"):
        call = RetellCallContext(
            call_id=str(call_id) if call_id else None,
            agent_id=str(payload["agent_id"]) if payload.get("agent_id") else None,
            from_number=str(from_number) if from_number else None,
            to_number=str(to_number) if to_number else None,
            direction=str(direction) if direction else None,
        )

    return RetellToolInvocation(name=tool_name.strip(), args=args, call=call)


class BolnaExecutionWebhook(BaseModel):
    """Subset of Bolna's post-call / status webhook execution payload."""

    model_config = ConfigDict(extra="allow")

    id: str | int | None = None
    status: str | None = None
    agent_id: str | None = None
    telephony_data: dict[str, Any] = Field(default_factory=dict)

    def external_call_id(self) -> str | None:
        telephony = self.telephony_data or {}
        raw = (
            telephony.get("provider_call_id")
            or telephony.get("call_sid")
            or self.id
        )
        if raw is None:
            return None
        return f"bolna:{raw}"
