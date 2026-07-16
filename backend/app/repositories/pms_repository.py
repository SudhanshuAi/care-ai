"""Persistence queries used by the asynchronous PMS synchronization path."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.appointment import Appointment
from app.db.models.enums import PmsSyncStatus


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
