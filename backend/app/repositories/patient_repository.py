from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.patient import Patient


class PatientRepository:
    """Read-only patient queries used by patient-resolution tools."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_phone(self, phone: str) -> list[Patient]:
        statement: Select[tuple[Patient]] = (
            select(Patient)
            .where(Patient.phone == phone.strip())
            .order_by(Patient.full_name)
        )
        return list((await self._session.scalars(statement)).all())

    async def by_name(self, name: str, limit: int = 20) -> list[Patient]:
        statement: Select[tuple[Patient]] = (
            select(Patient)
            .where(Patient.full_name.ilike(f"%{name.strip()}%"))
            .order_by(Patient.full_name)
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def by_id(self, patient_id: UUID) -> Patient | None:
        return await self._session.get(Patient, patient_id)
