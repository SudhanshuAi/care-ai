from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import FollowUpCategory, FollowUpStatus
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.call import Call
    from app.db.models.patient import Patient


class FollowUp(UUIDPkMixin, TimestampMixin, Base):
    """A logged item needing human attention: an escalation request, a
    clinical concern, or anything else outside the booking flow.

    The agent's only responsibility toward this table is to create the
    row and set the caller's expectation correctly ("someone will call
    you back") -- per the assignment, it must never imply an immediate
    live transfer that isn't actually happening.
    """

    __tablename__ = "followups"

    call_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL"), index=True
    )
    category: Mapped[FollowUpCategory] = mapped_column(
        SAEnum(
            FollowUpCategory,
            name="followup_category",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[FollowUpStatus] = mapped_column(
        SAEnum(
            FollowUpStatus,
            name="followup_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=FollowUpStatus.OPEN,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    call: Mapped[Call] = relationship(back_populates="followups")
    patient: Mapped[Patient | None] = relationship(back_populates="followups")

    def __repr__(self) -> str:
        return f"<FollowUp id={self.id} category={self.category} status={self.status}>"
