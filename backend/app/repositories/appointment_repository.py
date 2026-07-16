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
        """Load an appointment for mutation.

        Row-level ``FOR UPDATE`` is intentionally omitted so this works
        through Neon/PgBouncer transaction poolers. Concurrent writes
        for the same practitioner are serialized via
        ``pg_advisory_xact_lock`` in ``AppointmentService``, and
        overlapping bookings are still rejected by the DB exclusion
        constraint.
        """

        statement = (
            select(Appointment)
            .where(Appointment.id == appointment_id)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.practitioner),
                joinedload(Appointment.branch),
                joinedload(Appointment.appointment_type),
            )
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
