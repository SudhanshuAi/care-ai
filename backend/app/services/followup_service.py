from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.core.guardrails import (
    CALLBACK_EXPECTATION,
    notes_promise_immediate_transfer,
)
from app.core.logging import get_logger
from app.db.models.enums import FollowUpStatus
from app.db.models.followup import FollowUp
from app.repositories.followup_repository import FollowUpRepository
from app.schemas.tools import FollowUpRequest, FollowUpResponse

logger = get_logger(__name__)


class FollowUpService:
    def __init__(self, session: AsyncSession, repository: FollowUpRepository) -> None:
        self._session = session
        self._repository = repository

    async def create(self, request: FollowUpRequest) -> FollowUpResponse:
        notes = request.notes.strip()
        if not notes:
            raise ValidationError("notes must not be empty.")
        if notes_promise_immediate_transfer(notes):
            raise ValidationError(
                "Follow-up notes must not promise an immediate live human transfer. "
                "Log a callback request instead."
            )

        async with self._session.begin():
            existing = await self._repository.open_for_call_category(
                call_id=request.call_id,
                category=request.category,
            )
            if existing is not None:
                raise ConflictError(
                    "An open follow-up already exists for this call and category."
                )

            followup = FollowUp(
                call_id=request.call_id,
                patient_id=request.patient_id,
                category=request.category,
                status=FollowUpStatus.OPEN,
                notes=notes,
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
                callback_expectation=CALLBACK_EXPECTATION,
            )
