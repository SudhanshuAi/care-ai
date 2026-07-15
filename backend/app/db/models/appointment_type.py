from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment import Appointment
    from app.db.models.department import Department


class AppointmentType(UUIDPkMixin, TimestampMixin, Base):
    """A bookable service (e.g. "Dental Checkup", 30 minutes) within a
    department, carrying the policy fields the assignment explicitly
    tests for:

    * `buffer_minutes` -- required gap enforced *around* the
      appointment (not shrinking its own duration) so same-day slots
      don't get packed back-to-back when the clinic requires a gap.
    * `cancellation_fee` / `fee_window_hours` -- a fee is only
      applicable, and should only ever be mentioned to the caller, if
      the reschedule/cancellation happens within `fee_window_hours` of
      the appointment start. Both are nullable: many service types
      (e.g. a first consultation) have no fee policy at all.
    """

    __tablename__ = "appointment_types"

    department_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    cancellation_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    fee_window_hours: Mapped[int | None] = mapped_column(Integer)

    department: Mapped[Department] = relationship(back_populates="appointment_types")
    appointments: Mapped[list[Appointment]] = relationship(back_populates="appointment_type")

    def __repr__(self) -> str:
        return f"<AppointmentType id={self.id} name={self.name!r}>"
