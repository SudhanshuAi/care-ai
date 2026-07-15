from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.followup import FollowUp
from app.db.models.enums import FollowUpStatus
from app.repositories.followup_repository import FollowUpRepository
from app.schemas.tools import FollowUpRequest, FollowUpResponse

logger = get_logger(__name__)


class FollowUpService:
    def __init__(self, session: AsyncSession, repository: FollowUpRepository) -> None:
        self._session = session
        self._repository = repository

    async def create(self, request: FollowUpRequest) -> FollowUpResponse:
        async with self._session.begin():
            followup = FollowUp(
                call_id=request.call_id,
                patient_id=request.patient_id,
                category=request.category,
                status=FollowUpStatus.OPEN,
                notes=request.notes,
            )
            self._repository.add(followup)
            await self._session.flush()
            logger.info(
                "followup_created",
                followup_id=str(followup.id),
                category=followup.category.value,
            )
            return FollowUpResponse(
                followup_id=followup.id,
                status=followup.status.value,
                category=followup.category.value,
                created_at=followup.created_at,
            )
