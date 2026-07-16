"""Unit tests for conversation observability helpers."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
import structlog

from app.core.observability import (
    PROVIDER_RETELL,
    bind_conversation_context,
    bind_request_provider,
    conversation_state_snapshot,
    extract_appointment_id,
    extract_patient_id,
    resolve_conversation_id,
)


def test_bind_request_provider_from_path() -> None:
    structlog.contextvars.clear_contextvars()
    assert bind_request_provider("/webhooks/retell/tools") == PROVIDER_RETELL
    assert structlog.contextvars.get_contextvars()["provider"] == "retell"
    assert bind_request_provider("/tools/search_availability") == "rest"


def test_extract_ids_from_args_and_result() -> None:
    appointment_id = str(uuid4())
    patient_id = str(uuid4())
    # Prefer result (booking confirmation) over args.
    assert (
        extract_appointment_id({"appointment_id": str(uuid4())}, {"appointment_id": appointment_id})
        == appointment_id
    )
    assert extract_appointment_id({"appointment_id": appointment_id}, None) == appointment_id
    assert extract_patient_id({"patient_id": patient_id}) == patient_id
    assert (
        extract_patient_id(
            {},
            {
                "requires_disambiguation": False,
                "patients": [{"id": patient_id, "full_name": "Rahul"}],
            },
        )
        == patient_id
    )


def test_conversation_state_snapshot_is_compact() -> None:
    call = SimpleNamespace(
        current_intent="book",
        last_tool_called="search_availability",
        pending_confirmation={"type": "availability_options"},
        last_availability_search={"slots": []},
        status=SimpleNamespace(value="in_progress"),
    )
    snapshot = conversation_state_snapshot(call)  # type: ignore[arg-type]
    assert snapshot is not None
    assert snapshot["has_pending_confirmation"] is True
    assert snapshot["last_tool_called"] == "search_availability"
    assert "slots" not in snapshot


@pytest.mark.asyncio
async def test_resolve_conversation_id_walks_resume_chain() -> None:
    root_id = uuid4()
    mid_id = uuid4()
    leaf_id = uuid4()
    root = SimpleNamespace(id=root_id, resumed_from_call_id=None)
    mid = SimpleNamespace(id=mid_id, resumed_from_call_id=root_id)
    leaf = SimpleNamespace(id=leaf_id, resumed_from_call_id=mid_id)
    rows = {root_id: root, mid_id: mid, leaf_id: leaf}

    async def lookup(call_id):
        return rows.get(call_id)

    assert await resolve_conversation_id(call=leaf, lookup=lookup) == str(root_id)
    assert await resolve_conversation_id(call=root, lookup=lookup) == str(root_id)


def test_bind_conversation_context_merges_fields() -> None:
    structlog.contextvars.clear_contextvars()
    bind_conversation_context(
        provider=PROVIDER_RETELL,
        tool_name="lookup_patient",
        call_id="retell-1",
        conversation_id=str(uuid4()),
        patient_id=str(uuid4()),
        language="hi-IN",
        conversation_state={"current_intent": "identify"},
    )
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["provider"] == "retell"
    assert ctx["tool_name"] == "lookup_patient"
    assert ctx["language"] == "hi-IN"
    assert ctx["call_id"] == "retell-1"
