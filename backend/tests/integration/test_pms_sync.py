"""Integration coverage for durable mock-PMS write-back and retries."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Appointment, AppointmentType, Branch, Patient, Practitioner
from app.db.models.enums import AppointmentStatus, PmsSyncStatus
from app.db.models.mock_pms_appointment import MockPmsAppointment
from app.db.session import session_scope
from app.services.pms_sync_service import PmsSyncService
from scripts.seed_clinic import seed


class _FailingPmsAdapter:
    async def write_appointment(self, *_args, **_kwargs):
        raise RuntimeError("mock PMS temporarily unavailable")


@pytest.mark.asyncio
async def test_mock_pms_failure_retries_idempotently() -> None:
    await seed()
    async with session_scope() as session:
        patient = await session.scalar(select(Patient).limit(1))
        practitioner = await session.scalar(select(Practitioner).limit(1))
        branch = await session.scalar(select(Branch).limit(1))
        appointment_type = await session.scalar(select(AppointmentType).limit(1))
        assert patient and practitioner and branch and appointment_type
        start_time = datetime.now(UTC) + timedelta(
            days=365, minutes=uuid4().int % 1_000_000
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

    settings = Settings(pms_retry_max_attempts=2, pms_retry_base_seconds=0)
    failed = await PmsSyncService(
        settings=settings,
        adapter_factory=lambda _session: _FailingPmsAdapter(),
    ).sync_appointment(appointment_id)

    assert failed.status == PmsSyncStatus.PENDING_RETRY
    assert failed.attempted is True

    recovered = await PmsSyncService(settings=settings).retry_pending()
    recovered_target = next(
        result for result in recovered if result.appointment_id == appointment_id
    )
    assert recovered_target.status == PmsSyncStatus.SYNCED

    async with session_scope() as session:
        saved = await session.scalar(
            select(Appointment).where(Appointment.id == appointment_id)
        )
        receipt = await session.scalar(
            select(MockPmsAppointment).where(
                MockPmsAppointment.appointment_id == appointment_id
            )
        )
        assert saved is not None
        assert saved.pms_sync_status == PmsSyncStatus.SYNCED
        assert saved.pms_sync_attempts == 2
        assert saved.pms_last_error is None
        assert receipt is not None

    replay = await PmsSyncService(settings=settings).sync_appointment(appointment_id)
    assert replay.status == PmsSyncStatus.SYNCED
    assert replay.attempted is False
