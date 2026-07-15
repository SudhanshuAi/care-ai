from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Appointment, IdempotencyKey
from app.db.models.enums import IdempotencyOperationType


class AppointmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_id_for_update(self, appointment_id: UUID) -> Appointment | None:
        statement = (
            select(Appointment)
            .where(Appointment.id == appointment_id)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.practitioner),
                joinedload(Appointment.branch),
                joinedload(Appointment.appointment_type),
            )
            .with_for_update()
        )
        return await self._session.scalar(statement)

    async def idempotency_record(
        self, key: str, operation: IdempotencyOperationType
    ) -> IdempotencyKey | None:
        statement = select(IdempotencyKey).where(
            IdempotencyKey.key == key,
            IdempotencyKey.operation_type == operation,
        )
        return await self._session.scalar(statement)

    def add(self, appointment: Appointment) -> None:
        self._session.add(appointment)

    def add_idempotency_record(self, record: IdempotencyKey) -> None:
        self._session.add(record)
