from datetime import UTC, datetime
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

    async def list_for_patient(
        self, patient_id: UUID, *, upcoming_only: bool = True
    ) -> list[Appointment]:
        """List a patient's appointments so a caller who doesn't quote an
        appointment_id can still reschedule/cancel by voice.

        Without this, a voice agent has no legitimate way to discover the
        UUID of an appointment booked in a *previous* call and may
        hallucinate a placeholder instead of calling this first.
        """

        conditions = [Appointment.patient_id == patient_id]
        if upcoming_only:
            conditions.append(Appointment.status == AppointmentStatus.BOOKED)
            conditions.append(Appointment.start_time >= datetime.now(UTC))
        statement = (
            select(Appointment)
            .where(and_(*conditions))
            .options(
                joinedload(Appointment.practitioner),
                joinedload(Appointment.branch),
                joinedload(Appointment.appointment_type),
            )
            .order_by(Appointment.start_time.asc())
        )
        return list((await self._session.scalars(statement)).all())

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
