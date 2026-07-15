from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.db.models import AppointmentType, Branch, Patient
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
