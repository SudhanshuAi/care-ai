"""Unit tests for deterministic booking/follow-up guardrails."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ConflictError, ValidationError
from app.core.guardrails import (
    CALLBACK_EXPECTATION,
    notes_promise_immediate_transfer,
    require_caller_full_name,
)
from app.services.appointment_service import AppointmentService
from app.schemas.tools import CreateAppointmentRequest, FollowUpResponse


def test_require_caller_full_name_rejects_blank() -> None:
    with pytest.raises(ValidationError, match="caller_full_name is required"):
        require_caller_full_name("   ")


def test_require_caller_full_name_strips() -> None:
    assert require_caller_full_name("  Rahul Verma  ") == "Rahul Verma"


def test_create_request_rejects_whitespace_only_name() -> None:
    with pytest.raises(PydanticValidationError):
        CreateAppointmentRequest(
            patient_id=uuid4(),
            caller_full_name="   ",
            practitioner_id=uuid4(),
            branch_id=uuid4(),
            appointment_type_id=uuid4(),
            start_time=datetime.now(UTC),
        )


@pytest.mark.parametrize(
    "notes",
    [
        "I will transfer you now to a human agent.",
        "Connecting you immediately to a live person.",
        "Hold on while I transfer you to reception.",
        "You will be speaking with a live agent now.",
    ],
)
def test_notes_detect_immediate_transfer_promises(notes: str) -> None:
    assert notes_promise_immediate_transfer(notes) is True


def test_notes_allow_callback_wording() -> None:
    assert (
        notes_promise_immediate_transfer(
            "Caller asked for a human callback about billing."
        )
        is False
    )


def test_followup_response_includes_callback_expectation() -> None:
    response = FollowUpResponse(
        followup_id=uuid4(),
        status="open",
        category="human_requested",
        created_at=datetime.now(UTC),
    )
    assert response.callback_expectation == CALLBACK_EXPECTATION
    assert "immediate" in response.callback_expectation.lower()


def test_cancellation_fee_only_inside_window() -> None:
    far = SimpleNamespace(
        start_time=datetime.now(UTC) + timedelta(days=5),
        appointment_type=SimpleNamespace(
            cancellation_fee=Decimal("500.00"),
            fee_window_hours=24,
            currency="INR",
        ),
    )
    near = SimpleNamespace(
        start_time=datetime.now(UTC) + timedelta(hours=2),
        appointment_type=SimpleNamespace(
            cancellation_fee=Decimal("500.00"),
            fee_window_hours=24,
            currency="INR",
        ),
    )
    no_fee = SimpleNamespace(
        start_time=datetime.now(UTC) + timedelta(hours=1),
        appointment_type=SimpleNamespace(
            cancellation_fee=None,
            fee_window_hours=24,
            currency="INR",
        ),
    )

    assert AppointmentService._cancellation_fee(far).applicable is False
    applicable = AppointmentService._cancellation_fee(near)
    assert applicable.applicable is True
    assert applicable.amount == Decimal("500.00")
    assert AppointmentService._cancellation_fee(no_fee).applicable is False


@pytest.mark.asyncio
async def test_reject_patient_double_booking_raises_conflict() -> None:
    service = AppointmentService.__new__(AppointmentService)
    service._appointments = SimpleNamespace(
        patient_has_overlapping_booking=AsyncMock(return_value=True)
    )
    start = datetime.now(UTC)
    with pytest.raises(ConflictError, match="already has a booked appointment"):
        await service._reject_patient_double_booking(
            patient_id=uuid4(),
            start_time=start,
            end_time=start + timedelta(minutes=30),
        )


@pytest.mark.asyncio
async def test_reject_patient_double_booking_allows_free_patient() -> None:
    service = AppointmentService.__new__(AppointmentService)
    service._appointments = SimpleNamespace(
        patient_has_overlapping_booking=AsyncMock(return_value=False)
    )
    start = datetime.now(UTC)
    await service._reject_patient_double_booking(
        patient_id=uuid4(),
        start_time=start,
        end_time=start + timedelta(minutes=30),
    )
