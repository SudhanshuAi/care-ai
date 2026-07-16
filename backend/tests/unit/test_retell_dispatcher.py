from uuid import uuid4
from datetime import date

import pytest
from unittest.mock import MagicMock

from app.adapters.retell.dispatcher import RetellToolDispatcher
from app.adapters.retell.schemas import RetellCallContext, RetellToolInvocation
from app.schemas.tools import PatientLookupResponse, PatientSummary


class _StubPatientService:
    async def lookup_by_phone(self, phone: str) -> PatientLookupResponse:
        return PatientLookupResponse(
            match_count=2,
            requires_disambiguation=True,
            patients=[
                PatientSummary(
                    id=uuid4(),
                    full_name="Arjun Mehta",
                    phone=phone,
                    date_of_birth=date(1978, 6, 23),
                ),
                PatientSummary(
                    id=uuid4(),
                    full_name="Kavya Mehta",
                    phone=phone,
                    date_of_birth=date(1980, 9, 15),
                ),
            ],
        )

    async def lookup_by_name(self, name: str) -> PatientLookupResponse:
        return PatientLookupResponse(
            match_count=0, requires_disambiguation=False, patients=[]
        )


@pytest.mark.asyncio
async def test_lookup_patient_uses_phone_and_flags_disambiguation() -> None:
    dispatcher = RetellToolDispatcher(MagicMock())
    dispatcher._patient_service = _StubPatientService()  # type: ignore[method-assign]

    result = await dispatcher._lookup_patient(
        {"phone": "+91-98765-11111"},
        RetellCallContext(call_id="c1", from_number="+91-98765-11111"),
    )

    assert result["requires_disambiguation"] is True
    assert result["match_count"] == 2


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error_payload() -> None:
    dispatcher = RetellToolDispatcher(MagicMock())
    response = await dispatcher.dispatch(
        RetellToolInvocation(name="not_a_real_tool", args={}, call=None)
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_create_appointment_rejects_non_uuid_patient_id() -> None:
    """Retell sometimes passes a patient name where a UUID is required."""

    dispatcher = RetellToolDispatcher(MagicMock())
    response = await dispatcher.dispatch(
        RetellToolInvocation(
            name="create_appointment",
            args={
                "patient_id": "Rahul Verma",
                "caller_full_name": "Rahul Verma",
                "practitioner_name": "Dr. Ananya Rao",
                "branch_name": "Koramangala Branch",
                "appointment_type_name": "Dental Checkup",
                "start_time": "2026-07-23T09:00:00+05:30",
            },
            call=None,
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "validation_error"
    assert "patient_id" in response["error"]["detail"]
    assert "UUID" in response["error"]["detail"]


@pytest.mark.asyncio
async def test_lookup_falls_back_to_name_when_phone_misses() -> None:
    """Inbound caller ID often won't match seeded demo phones."""

    class _Stub:
        async def lookup_by_phone(self, phone: str) -> PatientLookupResponse:
            return PatientLookupResponse(
                match_count=0, requires_disambiguation=False, patients=[]
            )

        async def lookup_by_name(self, name: str) -> PatientLookupResponse:
            return PatientLookupResponse(
                match_count=1,
                requires_disambiguation=False,
                patients=[
                    PatientSummary(
                        id=uuid4(),
                        full_name="Rahul Verma",
                        phone="+91-98765-10001",
                        date_of_birth=date(1990, 4, 12),
                    )
                ],
            )

    dispatcher = RetellToolDispatcher(MagicMock())
    dispatcher._patient_service = _Stub()  # type: ignore[method-assign]

    result = await dispatcher._lookup_patient(
        {"phone": "+91-99999-00000", "full_name": "Rahul Verma"},
        RetellCallContext(call_id="c1", from_number="+91-99999-00000"),
    )

    assert result["match_count"] == 1
    assert result["patients"][0]["full_name"] == "Rahul Verma"
    assert result["lookup_strategy"] == "name_fallback_after_phone_miss"


@pytest.mark.asyncio
async def test_create_appointment_rejects_missing_patient_id() -> None:
    dispatcher = RetellToolDispatcher(MagicMock())
    response = await dispatcher.dispatch(
        RetellToolInvocation(
            name="create_appointment",
            args={
                "caller_full_name": "Rahul Verma",
                "start_time": "2026-07-23T09:00:00+05:30",
            },
            call=None,
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "validation_error"
    assert "patient_id" in response["error"]["detail"]
