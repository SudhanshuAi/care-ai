import pytest

from app.adapters.bolna.schemas import normalize_bolna_invocation
from app.adapters.bolna.security import verify_bolna_bearer
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
