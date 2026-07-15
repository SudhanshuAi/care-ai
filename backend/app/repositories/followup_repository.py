from app.db.models.followup import FollowUp
from sqlalchemy.ext.asyncio import AsyncSession


class FollowUpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, followup: FollowUp) -> None:
        self._session.add(followup)
