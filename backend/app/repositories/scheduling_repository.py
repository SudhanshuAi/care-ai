"""Persistence queries for scheduling.

This repository deliberately contains no slot-selection policy. It only
returns current database state; `AvailabilityService` decides what is a
valid candidate, keeping live-data access separate from business rules.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Appointment,
    AppointmentType,
    Branch,
    Practitioner,
    PractitionerBranch,
    PractitionerSchedule,
)
from app.db.models.enums import AppointmentStatus


class SchedulingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def appointment_type(self, appointment_type_id: UUID) -> AppointmentType | None:
        return await self._session.get(AppointmentType, appointment_type_id)

    async def eligible_schedules(
        self,
        *,
        department_id: UUID | None,
        practitioner_id: UUID | None,
        branch_id: UUID | None,
        local_date: date,
    ) -> list[PractitionerSchedule]:
        weekday = local_date.strftime("%A").lower()
        statement = (
            select(PractitionerSchedule)
            .join(PractitionerSchedule.practitioner)
            .join(PractitionerSchedule.branch)
            .where(
                PractitionerSchedule.is_active.is_(True),
                PractitionerSchedule.weekday == weekday,
                or_(
                    PractitionerSchedule.valid_from.is_(None),
                    PractitionerSchedule.valid_from <= local_date,
                ),
                or_(
                    PractitionerSchedule.valid_to.is_(None),
                    PractitionerSchedule.valid_to >= local_date,
                ),
            )
            .options(
                selectinload(PractitionerSchedule.practitioner),
                selectinload(PractitionerSchedule.branch),
            )
        )
        if department_id is not None:
            statement = statement.where(Practitioner.department_id == department_id)
        if practitioner_id is not None:
            statement = statement.where(PractitionerSchedule.practitioner_id == practitioner_id)
        if branch_id is not None:
            statement = statement.where(PractitionerSchedule.branch_id == branch_id)
        return list((await self._session.scalars(statement)).all())

    async def booked_appointments(
        self,
        *,
        practitioner_id: UUID,
        period_start: datetime,
        period_end: datetime,
        exclude_appointment_id: UUID | None = None,
    ) -> list[Appointment]:
        statement = (
            select(Appointment)
            .where(
                Appointment.practitioner_id == practitioner_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.start_time < period_end,
                Appointment.end_time > period_start,
            )
            .order_by(Appointment.start_time)
        )
        if exclude_appointment_id is not None:
            statement = statement.where(Appointment.id != exclude_appointment_id)
        return list((await self._session.scalars(statement)).all())

    async def practitioner(self, practitioner_id: UUID) -> Practitioner | None:
        return await self._session.get(Practitioner, practitioner_id)

    async def practitioner_at_branch(
        self, practitioner_id: UUID, branch_id: UUID
    ) -> Practitioner | None:
        statement = (
            select(Practitioner)
            .join(PractitionerBranch)
            .where(
                Practitioner.id == practitioner_id,
                PractitionerBranch.branch_id == branch_id,
            )
        )
        return await self._session.scalar(statement)

    async def branch(self, branch_id: UUID) -> Branch | None:
        return await self._session.get(Branch, branch_id)
