from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Appointment, IdempotencyKey
from app.db.models.enums import AppointmentStatus, IdempotencyOperationType


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

    async def patient_has_overlapping_booking(
        self,
        *,
        patient_id: UUID,
        start_time: datetime,
        end_time: datetime,
        exclude_appointment_id: UUID | None = None,
    ) -> bool:
        """True if this patient already has a BOOKED appointment overlapping this range.

        Guards against a patient being double-booked across two different
        practitioners/branches -- something the practitioner-scoped
        ``uq_appointment_no_overlap`` exclusion constraint cannot catch on
        its own, since it only rejects overlaps for the *same*
        practitioner. This is an application-level check backed by the
        matching ``uq_appointment_patient_no_overlap`` DB constraint.
        """

        conditions = [
            Appointment.patient_id == patient_id,
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        ]
        if exclude_appointment_id is not None:
            conditions.append(Appointment.id != exclude_appointment_id)
        statement = select(func.count()).select_from(Appointment).where(and_(*conditions))
        count = await self._session.scalar(statement)
        return bool(count)

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
