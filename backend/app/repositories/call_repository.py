from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.call import Call
from app.db.models.enums import CallDirection, CallStatus


class CallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_retell_call_id(self, retell_call_id: str) -> Call | None:
        statement = select(Call).where(Call.retell_call_id == retell_call_id)
        return await self._session.scalar(statement)

    async def ensure_from_retell(
        self,
        *,
        retell_call_id: str,
        phone: str,
        direction: CallDirection = CallDirection.INBOUND,
    ) -> Call:
        existing = await self.by_retell_call_id(retell_call_id)
        if existing is not None:
            return existing

        call = Call(
            retell_call_id=retell_call_id,
            phone=phone,
            direction=direction,
            status=CallStatus.IN_PROGRESS,
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

    async def by_id(self, call_id: UUID) -> Call | None:
        return await self._session.get(Call, call_id)
