from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import FollowUpCategory, FollowUpStatus
from app.db.models.followup import FollowUp


class FollowUpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, followup: FollowUp) -> None:
        self._session.add(followup)

    async def open_for_call_category(
        self, *, call_id: UUID, category: FollowUpCategory
    ) -> FollowUp | None:
        statement = (
            select(FollowUp)
            .where(
                FollowUp.call_id == call_id,
                FollowUp.category == category,
                FollowUp.status == FollowUpStatus.OPEN,
            )
            .order_by(FollowUp.created_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)
