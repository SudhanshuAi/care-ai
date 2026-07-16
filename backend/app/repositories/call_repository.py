from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.call import Call
from app.db.models.enums import CallDirection, CallStatus


class CallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_retell_call_id(self, retell_call_id: str) -> Call | None:
        statement = select(Call).where(Call.retell_call_id == retell_call_id)
        return await self._session.scalar(statement)

    async def latest_resumable_for_phone(
        self, phone: str, *, exclude_retell_call_id: str | None = None
    ) -> Call | None:
        """Return the most recent explicitly disconnected call for recovery.

        An `in_progress` row may be a genuinely concurrent call or a
        stale row whose provider end webhook was delayed. Auto-resuming
        it would risk carrying unrelated context into a new call, so
        only a confirmed disconnect is eligible without Retell's
        explicit `resumed_from_call_id`.
        """

        statement = (
            select(Call)
            .where(
                Call.phone == phone,
                Call.status == CallStatus.DISCONNECTED,
            )
            .order_by(desc(Call.last_updated_at), desc(Call.created_at))
            .limit(1)
        )
        if exclude_retell_call_id is not None:
            statement = statement.where(Call.retell_call_id != exclude_retell_call_id)
        return await self._session.scalar(statement)

    async def ensure_from_retell(
        self,
        *,
        retell_call_id: str,
        phone: str,
        direction: CallDirection = CallDirection.INBOUND,
        resumed_from_call_id: UUID | None = None,
    ) -> Call:
        existing = await self.by_retell_call_id(retell_call_id)
        if existing is not None:
            return existing

        call = Call(
            retell_call_id=retell_call_id,
            phone=phone,
            direction=direction,
            status=CallStatus.IN_PROGRESS,
            resumed_from_call_id=resumed_from_call_id,
        )
        self._session.add(call)
        await self._session.flush()
        return call

    async def mark_completed(self, retell_call_id: str) -> Call | None:
        call = await self.by_retell_call_id(retell_call_id)
        if call is None:
            return None
        call.status = CallStatus.COMPLETED
        await self._session.flush()
        return call

    async def mark_disconnected(self, retell_call_id: str) -> Call | None:
        call = await self.by_retell_call_id(retell_call_id)
        if call is None:
            return None
        call.status = CallStatus.DISCONNECTED
        call.disconnected_at = datetime.now(UTC)
        await self._session.flush()
        return call

    async def by_id(self, call_id: UUID) -> Call | None:
        return await self._session.get(Call, call_id)
