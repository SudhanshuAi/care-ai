"""Durable mock PMS provider used for production-like integration tests."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.appointment import Appointment
from app.db.models.mock_pms_appointment import MockPmsAppointment
from app.pms.protocol import PmsWritebackResult


class MockPmsAdapter:
    """Write an idempotent PMS receipt in a dedicated mock-PMS table."""

    provider = "mock"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_appointment(
        self, appointment: Appointment, *, idempotency_key: str
    ) -> PmsWritebackResult:
        statement = select(MockPmsAppointment).where(
            MockPmsAppointment.appointment_id == appointment.id
        )
        existing = await self._session.scalar(statement)
        if existing is not None:
            return PmsWritebackResult(
                provider=self.provider,
                external_reference=str(existing.id),
                replayed=True,
            )

        receipt = MockPmsAppointment(
            appointment_id=appointment.id,
            idempotency_key=idempotency_key,
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "practitioner_id": str(appointment.practitioner_id),
                "branch_id": str(appointment.branch_id),
                "appointment_type_id": str(appointment.appointment_type_id),
                "start_time": appointment.start_time.isoformat(),
                "end_time": appointment.end_time.isoformat(),
                "status": appointment.status.value,
            },
        )
        self._session.add(receipt)
        await self._session.flush()
        return PmsWritebackResult(
            provider=self.provider,
            external_reference=str(receipt.id),
        )
