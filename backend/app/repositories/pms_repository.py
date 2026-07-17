"""Persistence queries used by the asynchronous PMS synchronization path."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.appointment import Appointment
from app.db.models.enums import AppointmentStatus, PmsSyncStatus
from app.db.models.mock_pms_appointment import MockPmsAppointment


class PmsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def appointment_for_sync(self, appointment_id: UUID) -> Appointment | None:
        statement = (
            select(Appointment)
            .where(Appointment.id == appointment_id)
            .options(
                selectinload(Appointment.patient),
                selectinload(Appointment.practitioner),
                selectinload(Appointment.branch),
                selectinload(Appointment.appointment_type),
            )
        )
        return await self._session.scalar(statement)

    async def retry_candidates(self, *, limit: int) -> list[Appointment]:
        statement = (
            select(Appointment)
            .where(
                Appointment.pms_sync_status.in_(
                    (PmsSyncStatus.PENDING, PmsSyncStatus.PENDING_RETRY)
                )
            )
            .order_by(
                Appointment.pms_last_attempt_at.asc().nullsfirst(),
                Appointment.created_at.asc(),
            )
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_appointments(
        self,
        *,
        status: AppointmentStatus | None = None,
        pms_sync_status: PmsSyncStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Appointment], int]:
        filters = []
        if status is not None:
            filters.append(Appointment.status == status)
        if pms_sync_status is not None:
            filters.append(Appointment.pms_sync_status == pms_sync_status)

        count_statement = select(func.count()).select_from(Appointment)
        list_statement = (
            select(Appointment)
            .options(
                selectinload(Appointment.patient),
                selectinload(Appointment.practitioner),
                selectinload(Appointment.branch),
                selectinload(Appointment.appointment_type),
            )
            .order_by(Appointment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if filters:
            count_statement = count_statement.where(*filters)
            list_statement = list_statement.where(*filters)

        total = int(await self._session.scalar(count_statement) or 0)
        items = list((await self._session.scalars(list_statement)).all())
        return items, total

    async def appointment_detail(self, appointment_id: UUID) -> Appointment | None:
        return await self.appointment_for_sync(appointment_id)

    async def receipts_for_appointment(
        self, appointment_id: UUID
    ) -> list[MockPmsAppointment]:
        statement = (
            select(MockPmsAppointment)
            .where(MockPmsAppointment.appointment_id == appointment_id)
            .order_by(MockPmsAppointment.received_at.asc())
        )
        return list((await self._session.scalars(statement)).all())

    async def receipt_counts(
        self, appointment_ids: list[UUID]
    ) -> dict[UUID, int]:
        if not appointment_ids:
            return {}
        statement = (
            select(
                MockPmsAppointment.appointment_id,
                func.count().label("receipt_count"),
            )
            .where(MockPmsAppointment.appointment_id.in_(appointment_ids))
            .group_by(MockPmsAppointment.appointment_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {row.appointment_id: int(row.receipt_count) for row in rows}

    async def list_receipts(
        self,
        *,
        operation: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MockPmsAppointment], int]:
        filters = []
        if operation:
            filters.append(MockPmsAppointment.operation == operation)

        count_statement = select(func.count()).select_from(MockPmsAppointment)
        list_statement = (
            select(MockPmsAppointment)
            .order_by(MockPmsAppointment.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if filters:
            count_statement = count_statement.where(*filters)
            list_statement = list_statement.where(*filters)

        total = int(await self._session.scalar(count_statement) or 0)
        items = list((await self._session.scalars(list_statement)).all())
        return items, total
