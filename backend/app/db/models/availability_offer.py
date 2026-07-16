"""Short-lived offers produced by live availability search.

Booking and reschedule must consume a matching unexpired offer. This is
how the backend rejects bookings that skip search, reuse a stale slot,
or double-confirm the same offer.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin


class AvailabilityOffer(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "availability_offers"
    __table_args__ = (
        Index(
            "ix_availability_offers_slot_lookup",
            "practitioner_id",
            "branch_id",
            "appointment_type_id",
            "start_time",
        ),
        Index("ix_availability_offers_expires_at", "expires_at"),
    )

    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
    )
    appointment_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("appointment_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
    )

    def __repr__(self) -> str:
        return (
            f"<AvailabilityOffer practitioner_id={self.practitioner_id} "
            f"start_time={self.start_time} expires_at={self.expires_at}>"
        )
