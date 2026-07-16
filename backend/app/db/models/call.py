from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import CallDirection, CallStatus
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment import Appointment
    from app.db.models.call_turn import CallTurn
    from app.db.models.followup import FollowUp
    from app.db.models.patient import Patient


class Call(UUIDPkMixin, TimestampMixin, Base):
    """One phone call, inbound or outbound.

    `resumed_from_call_id` is a self-referential FK linking a call back
    to an earlier one it continues. This is the concrete, queryable
    mechanism behind two required scenarios:

    * Dropped-call recovery: caller hangs up mid-conversation, calls
      back shortly after -- the new `Call` row gets
      `resumed_from_call_id` set to the disconnected one, so the
      orchestrator preloads its state instead of starting cold.
    * Missed outbound call, callback: an outbound call goes unanswered;
      when the same number calls in, it's linked back the same way.

    `retell_call_id` is the id Retell assigns; kept nullable + unique
    since rows can also be created for planning an outbound call before
    Retell has dialed it.
    """

    __tablename__ = "calls"

    retell_call_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), index=True
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[CallDirection] = mapped_column(
        SAEnum(
            CallDirection,
            name="call_direction",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[CallStatus] = mapped_column(
        SAEnum(
            CallStatus,
            name="call_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CallStatus.IN_PROGRESS,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumed_from_call_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL")
    )
    detected_language_mix: Mapped[str | None] = mapped_column(String(32))
    # Durable conversation state. These fields are intentionally on
    # Call rather than in an in-memory cache: a reconnect can occur on
    # a different process after a deploy or container restart.
    language: Mapped[str | None] = mapped_column(String(32))
    current_intent: Mapped[str | None] = mapped_column(String(64))
    identified_patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), index=True
    )
    selected_branch_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL")
    )
    selected_practitioner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="SET NULL")
    )
    selected_appointment_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("appointment_types.id", ondelete="SET NULL")
    )
    last_availability_search: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    pending_confirmation: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    conversation_summary: Mapped[str | None] = mapped_column(Text)
    last_tool_called: Mapped[str | None] = mapped_column(String(64))
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    patient: Mapped[Patient | None] = relationship(
        back_populates="calls", foreign_keys=[patient_id]
    )
    identified_patient: Mapped[Patient | None] = relationship(
        foreign_keys=[identified_patient_id]
    )
    resumed_from_call: Mapped[Call | None] = relationship(
        remote_side="Call.id", foreign_keys=[resumed_from_call_id]
    )
    turns: Mapped[list[CallTurn]] = relationship(
        back_populates="call",
        cascade="all, delete-orphan",
        order_by="CallTurn.turn_index",
    )
    appointments_created: Mapped[list[Appointment]] = relationship(
        back_populates="created_by_call"
    )
    followups: Mapped[list[FollowUp]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Call id={self.id} phone={self.phone!r} status={self.status}>"
