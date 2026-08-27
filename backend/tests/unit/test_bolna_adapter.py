from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.adapters.bolna.schemas import BolnaExecutionWebhook, normalize_bolna_invocation
from app.adapters.bolna.security import verify_bolna_bearer
from app.adapters.retell.dispatcher import RetellToolDispatcher
from app.adapters.retell.schemas import RetellCallContext
from app.core.exceptions import ValidationError


def test_normalize_maps_path_tool_and_call_context() -> None:
    invocation = normalize_bolna_invocation(
        "lookup_patient",
        {
            "full_name": "Rahul Verma",
            "from_number": "+91-98765-10001",
            "call_sid": "CA123",
            "earliest_only": "false",
        },
    )

    assert invocation.name == "lookup_patient"
    assert invocation.args["full_name"] == "Rahul Verma"
    assert "from_number" not in invocation.args
    assert invocation.call is not None
    assert invocation.call.call_id == "bolna:CA123"
    assert invocation.call.from_number == "+91-98765-10001"


def test_normalize_reads_telephony_data_block() -> None:
    invocation = normalize_bolna_invocation(
        "create_followup",
        {
            "category": "human_requested",
            "notes": "Needs callback",
            "telephony_data": {
                "from_number": "+919876510001",
                "provider_call_id": "CA999",
                "call_type": "inbound",
            },
        },
    )

    assert invocation.call is not None
    assert invocation.call.call_id == "bolna:CA999"
    assert invocation.call.from_number == "+919876510001"
    assert invocation.call.direction == "inbound"


def test_normalize_coerces_string_booleans_from_bolna() -> None:
    invocation = normalize_bolna_invocation(
        "search_availability",
        {
            "appointment_type_name": "Dental Checkup",
            "earliest_only": "true",
            "limit": "3",
        },
    )

    assert invocation.args["earliest_only"] is True
    assert invocation.args["limit"] == 3

    list_invocation = normalize_bolna_invocation(
        "list_appointments",
        {"caller_full_name": "Rahul Verma", "upcoming_only": "false"},
    )
    assert list_invocation.args["upcoming_only"] is False


def test_normalize_discards_missing_chat_context_placeholders() -> None:
    invocation = normalize_bolna_invocation(
        "lookup_patient",
        {
            "full_name": "Rahul Verma",
            "phone": "%(phone)s",
            "from_number": "None",
            "call_sid": "None",
        },
    )

    assert invocation.args == {"full_name": "Rahul Verma"}
    assert invocation.call is None


def test_execution_webhook_accepts_null_telephony_data() -> None:
    webhook = BolnaExecutionWebhook.model_validate({"id": "chat-execution", "telephony_data": None})

    assert webhook.telephony_data == {}
    assert webhook.external_call_id() == "bolna:chat-execution"


def test_verify_bolna_bearer_accepts_matching_token() -> None:
    verify_bolna_bearer(
        authorization_header="Bearer secret-token",
        api_token="secret-token",
    )
    verify_bolna_bearer(
        authorization_header="Bearer secret-token",
        api_token="Bearer secret-token",
    )


def test_verify_bolna_bearer_rejects_bad_token() -> None:
    with pytest.raises(ValidationError, match="Invalid Bolna"):
        verify_bolna_bearer(
            authorization_header="Bearer wrong",
            api_token="secret-token",
        )


def test_verify_bolna_bearer_requires_header() -> None:
    with pytest.raises(ValidationError, match="Missing Authorization"):
        verify_bolna_bearer(authorization_header=None, api_token="secret-token")


def test_bolna_mutation_idempotency_key_uses_provider_prefix() -> None:
    dispatcher = RetellToolDispatcher(MagicMock(), provider="bolna")

    key = dispatcher._idempotency_key(
        "create_appointment",
        RetellCallContext(call_id="bolna:CA123"),
        {"patient_id": "patient-1"},
    )

    assert key.startswith("bolna:CA123:create_appointment:")


@pytest.mark.asyncio
async def test_bolna_resolves_the_only_upcoming_appointment() -> None:
    dispatcher = RetellToolDispatcher(MagicMock(), provider="bolna")
    patient_id = uuid4()
    appointment_id = uuid4()
    dispatcher._resolve_patient_id = AsyncMock(return_value=patient_id)
    dispatcher._appointment_service.list_for_patient = AsyncMock(
        return_value=[SimpleNamespace(appointment_id=appointment_id)]
    )

    resolved = await dispatcher._resolve_appointment_id({"caller_full_name": "Rahul Verma"}, None)

    assert resolved == appointment_id
    dispatcher._appointment_service.list_for_patient.assert_awaited_once_with(
        patient_id, upcoming_only=True
    )


@pytest.mark.asyncio
async def test_bolna_never_guesses_between_multiple_appointments() -> None:
    dispatcher = RetellToolDispatcher(MagicMock(), provider="bolna")
    dispatcher._resolve_patient_id = AsyncMock(return_value=uuid4())
    dispatcher._appointment_service.list_for_patient = AsyncMock(
        return_value=[
            SimpleNamespace(appointment_id=uuid4()),
            SimpleNamespace(appointment_id=uuid4()),
        ]
    )

    with pytest.raises(ValidationError, match="More than one upcoming appointment"):
        await dispatcher._resolve_appointment_id({"caller_full_name": "Rahul Verma"}, None)
