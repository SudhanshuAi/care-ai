from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Appointment, AppointmentType, Branch, Call, Patient
from app.db.models.enums import PmsSyncStatus
from app.db.models.mock_pms_appointment import MockPmsAppointment
from app.db.session import session_scope
from app.main import app
from scripts.seed_clinic import seed


async def _seed_ids() -> tuple[str, str, str]:
    await seed()
    async with session_scope() as session:
        appointment_type = await session.scalar(select(AppointmentType).limit(1))
        branch = await session.scalar(select(Branch).order_by(Branch.name).limit(1))
        patient = await session.scalar(select(Patient).where(Patient.full_name == "Rahul Verma"))
        assert appointment_type and branch and patient
        return str(appointment_type.id), str(branch.id), str(patient.id)


@pytest.mark.asyncio
async def test_phone_lookup_returns_explicit_disambiguation() -> None:
    await seed()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/tools/patients/by-phone", params={"phone": "+91-98765-11111"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["match_count"] == 2
    assert body["requires_disambiguation"] is True


@pytest.mark.asyncio
async def test_create_appointment_is_idempotent() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    target_date = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        availability = await client.post(
            "/tools/search_availability",
            json={
                "appointment_type_id": appointment_type_id,
                "branch_id": branch_id,
                "appointment_date": target_date,
                "limit": 1,
            },
        )
        assert availability.status_code == 200
        slots = availability.json()["slots"]
        if not slots:
            pytest.skip("Seeded branch has no schedule on the generated date.")
        slot = slots[0]
        payload = {
            "patient_id": patient_id,
            "caller_full_name": "Rahul Verma",
            "practitioner_id": slot["practitioner_id"],
            "branch_id": slot["branch_id"],
            "appointment_type_id": appointment_type_id,
            "start_time": slot["start_time"],
        }
        key = f"test-booking-{uuid4()}"
        first = await client.post(
            "/tools/create_appointment",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        replay = await client.post(
            "/tools/create_appointment",
            json=payload,
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["appointment_id"] == first.json()["appointment_id"]
    assert replay.json()["idempotent_replay"] is True
    appointment_id = first.json()["appointment_id"]
    async with session_scope() as session:
        appointment = await session.get(Appointment, appointment_id)
        receipt = await session.scalar(
            select(MockPmsAppointment).where(
                MockPmsAppointment.appointment_id == appointment_id
            )
        )
    assert appointment is not None
    assert appointment.pms_sync_status == PmsSyncStatus.SYNCED
    assert receipt is not None


@pytest.mark.asyncio
async def test_retell_booking_links_appointment_to_call() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    target_date = (datetime.now(UTC).date() + timedelta(days=14)).isoformat()
    call_id = f"retell-booking-{uuid4()}"
    call = {
        "call_id": call_id,
        "from_number": "+91-98765-10001",
        "language": "en-IN",
    }
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        availability = await client.post(
            "/webhooks/retell/tools",
            json={
                "name": "search_availability",
                "args": {
                    "appointment_type_id": appointment_type_id,
                    "branch_id": branch_id,
                    "appointment_date": target_date,
                    "limit": 1,
                },
                "call": call,
            },
        )
        assert availability.status_code == 200
        slots = availability.json()["result"]["slots"]
        if not slots:
            pytest.skip("Seeded branch has no schedule on the generated date.")
        slot = slots[0]
        booking = await client.post(
            "/webhooks/retell/tools",
            json={
                "name": "create_appointment",
                "args": {
                    "patient_id": patient_id,
                    "caller_full_name": "Rahul Verma",
                    "practitioner_id": slot["practitioner_id"],
                    "branch_id": slot["branch_id"],
                    "appointment_type_id": appointment_type_id,
                    "start_time": slot["start_time"],
                },
                "call": call,
            },
        )

    assert booking.status_code == 200
    body = booking.json()
    assert body["ok"] is True
    appointment_id = body["result"]["appointment_id"]
    async with session_scope() as session:
        appointment = await session.scalar(
            select(Appointment).where(Appointment.id == appointment_id)
        )
        database_call = await session.scalar(
            select(Call).where(Call.retell_call_id == call_id)
        )
    assert appointment is not None
    assert database_call is not None
    assert appointment.created_by_call_id == database_call.id


@pytest.mark.asyncio
async def test_retell_reconnect_restores_call_context() -> None:
    await seed()
    original_call_id = f"retell-original-{uuid4()}"
    resumed_call_id = f"retell-resumed-{uuid4()}"
    transport = httpx.ASGITransport(app=app)
    original_payload = {
        "name": "lookup_patient",
        "args": {"phone": "+91-98765-10001"},
        "call": {
            "call_id": original_call_id,
            "from_number": "+91-98765-10001",
            "language": "en-IN",
        },
    }
    resumed_payload = {
        "name": "lookup_patient",
        "args": {"phone": "+91-98765-10001"},
        "call": {
            "call_id": resumed_call_id,
            "resumed_from_call_id": original_call_id,
            "from_number": "+91-98765-10001",
            "language": "en-IN",
        },
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/webhooks/retell/tools", json=original_payload)
        assert first.status_code == 200
        resumed = await client.post("/webhooks/retell/tools", json=resumed_payload)
        context = await client.get(f"/webhooks/retell/call-context/{resumed_call_id}")

    assert resumed.status_code == 200
    assert context.status_code == 200
    body = context.json()
    assert body["resumed_from_retell_call_id"] == original_call_id
    assert body["restored"] is True
    assert body["identified_patient_id"] is not None
    assert body["last_tool_called"] == "lookup_patient"


@pytest.mark.asyncio
async def test_retell_call_ended_persists_summary_even_without_tool_use() -> None:
    call_id = f"retell-ended-{uuid4()}"
    transport = httpx.ASGITransport(app=app)
    payload = {
        "call": {
            "call_id": call_id,
            "from_number": "+91-98765-10001",
            "call_status": "completed",
            "language": "hi-IN",
        }
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ended = await client.post("/webhooks/retell/call-ended", json=payload)
        context = await client.get(f"/webhooks/retell/call-context/{call_id}")

    assert ended.status_code == 200
    assert ended.json()["updated"] is True
    assert ended.json()["conversation_summary"]
    assert context.json()["language"] == "hi-IN"


@pytest.mark.asyncio
async def test_retell_call_ended_ignores_non_terminal_status() -> None:
    call_id = f"retell-in-progress-{uuid4()}"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/retell/call-ended",
            json={
                "call": {
                    "call_id": call_id,
                    "from_number": "+91-98765-10001",
                    "call_status": "in_progress",
                }
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "updated": False,
        "reason": "non_terminal_status",
    }


@pytest.mark.asyncio
async def test_same_phone_callback_restores_disconnected_call() -> None:
    disconnected_call_id = f"retell-disconnected-{uuid4()}"
    callback_call_id = f"retell-callback-{uuid4()}"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/webhooks/retell/call-ended",
            json={
                "call": {
                    "call_id": disconnected_call_id,
                    "from_number": "+91-98765-10002",
                    "call_status": "disconnected",
                    "language": "hi-IN",
                }
            },
        )
        callback = await client.post(
            "/webhooks/retell/tools",
            json={
                "name": "lookup_patient",
                "args": {"phone": "+91-98765-10002"},
                "call": {
                    "call_id": callback_call_id,
                    "from_number": "+91-98765-10002",
                },
            },
        )
        context = await client.get(
            f"/webhooks/retell/call-context/{callback_call_id}"
        )

    assert callback.status_code == 200
    assert context.json()["restored"] is True
    assert context.json()["resumed_from_retell_call_id"] == disconnected_call_id
