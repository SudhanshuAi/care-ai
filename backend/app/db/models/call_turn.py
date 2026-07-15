from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import TurnRole
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.call import Call


class CallTurn(UUIDPkMixin, TimestampMixin, Base):
    """One turn of a call transcript.

    The four `*_ms` columns are the raw material for the eval
    harness's "latency broken down by component" requirement: rather
    than re-deriving ASR/LLM/tool/TTS timing after the fact from logs,
    the orchestrator records it turn-by-turn as it happens. `tool_called`
    records which tool (if any) fired on this turn, so "how many turns
    to a confirmed booking" and "how often a redundant question gets
    asked" can both be computed directly from this table later.
    """

    __tablename__ = "call_turns"
    __table_args__ = (
        UniqueConstraint("call_id", "turn_index", name="uq_call_turn_index"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[TurnRole] = mapped_column(
        SAEnum(
            TurnRole,
            name="turn_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    language_detected: Mapped[str | None] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tool_called: Mapped[str | None] = mapped_column(String(64))

    asr_latency_ms: Mapped[int | None] = mapped_column(Integer)
    llm_ttft_ms: Mapped[int | None] = mapped_column(Integer)
    tool_latency_ms: Mapped[int | None] = mapped_column(Integer)
    tts_first_byte_ms: Mapped[int | None] = mapped_column(Integer)

    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    call: Mapped[Call] = relationship(back_populates="turns")

    def __repr__(self) -> str:
        return f"<CallTurn call_id={self.call_id} turn_index={self.turn_index} role={self.role}>"
