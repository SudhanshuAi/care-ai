from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.availability_offer import AvailabilityOffer


class AvailabilityOfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, offer: AvailabilityOffer) -> None:
        self._session.add(offer)

    async def persist_new(self, offers: list[AvailabilityOffer]) -> None:
        """Commit newly searched offers so a later booking request can consume them.

        Reads during search already autobegin a transaction on this session,
        so we must not call ``begin()`` again — just flush and commit.
        """

        if not offers:
            return
        for offer in offers:
            self._session.add(offer)
        await self._session.commit()

    async def find_active_offer(
        self,
        *,
        practitioner_id: UUID,
        branch_id: UUID,
        appointment_type_id: UUID,
        start_time: datetime,
    ) -> AvailabilityOffer | None:
        now = datetime.now(UTC)
        statement = (
            select(AvailabilityOffer)
            .where(
                AvailabilityOffer.practitioner_id == practitioner_id,
                AvailabilityOffer.branch_id == branch_id,
                AvailabilityOffer.appointment_type_id == appointment_type_id,
                AvailabilityOffer.start_time == start_time.astimezone(UTC),
                AvailabilityOffer.consumed_at.is_(None),
                AvailabilityOffer.expires_at > now,
            )
            .order_by(AvailabilityOffer.searched_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def find_matching_offer_any_state(
        self,
        *,
        practitioner_id: UUID,
        branch_id: UUID,
        appointment_type_id: UUID,
        start_time: datetime,
    ) -> AvailabilityOffer | None:
        """Return the newest matching offer, even if expired or consumed."""

        statement = (
            select(AvailabilityOffer)
            .where(
                AvailabilityOffer.practitioner_id == practitioner_id,
                AvailabilityOffer.branch_id == branch_id,
                AvailabilityOffer.appointment_type_id == appointment_type_id,
                AvailabilityOffer.start_time == start_time.astimezone(UTC),
            )
            .order_by(AvailabilityOffer.searched_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)
