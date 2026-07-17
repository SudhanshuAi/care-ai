"""Admin mock-PMS console API coverage."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Appointment, AppointmentType, Branch, Patient, Practitioner
from app.db.models.enums import AppointmentStatus, PmsSyncStatus
from app.db.session import session_scope
from app.main import app
from app.services.pms_sync_service import PmsSyncService
from scripts.seed_clinic import seed


@pytest.mark.asyncio
async def test_admin_pms_lists_appointment_and_receipts() -> None:
    await seed()
    async with session_scope() as session:
        patient = await session.scalar(select(Patient).limit(1))
        practitioner = await session.scalar(select(Practitioner).limit(1))
        branch = await session.scalar(select(Branch).limit(1))
        appointment_type = await session.scalar(select(AppointmentType).limit(1))
        assert patient and practitioner and branch and appointment_type
        start_time = datetime.now(UTC) + timedelta(
            days=300, minutes=uuid4().int % 1_000_000
        )
        appointment = Appointment(
            patient_id=patient.id,
            practitioner_id=practitioner.id,
            branch_id=branch.id,
            appointment_type_id=appointment_type.id,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=30),
            status=AppointmentStatus.BOOKED,
            pms_sync_status=PmsSyncStatus.PENDING,
        )
        session.add(appointment)
        await session.flush()
        appointment_id = appointment.id

    await PmsSyncService().sync_appointment(appointment_id, operation="create")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await client.get("/admin/pms/appointments")
        detail = await client.get(f"/admin/pms/appointments/{appointment_id}")
        receipts = await client.get("/admin/pms/receipts")

    assert listed.status_code == 200
    assert any(
        item["appointment_id"] == str(appointment_id) for item in listed.json()["items"]
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["receipt_count"] >= 1
    assert body["receipts"][0]["operation"] == "create"
    assert receipts.status_code == 200
    assert receipts.json()["total"] >= 1
