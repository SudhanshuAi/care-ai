from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment import Appointment
    from app.db.models.clinic import Clinic
    from app.db.models.practitioner_branch import PractitionerBranch
    from app.db.models.practitioner_schedule import PractitionerSchedule


class Branch(UUIDPkMixin, TimestampMixin, Base):
    """One physical clinic location.

    `timezone` is an explicit IANA name (e.g. "Asia/Kolkata"), stored
    per branch rather than assumed globally, so "today"/"tomorrow" and
    working-hours math is always done in the branch's actual local
    time -- this is the concrete fix for the "UTC bug shifts today to
    tomorrow" failure mode called out in the assignment, and it also
    lets a future branch in a different timezone (e.g. a UK location)
    work correctly without code changes.
    """

    __tablename__ = "branches"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))

    clinic: Mapped[Clinic] = relationship(back_populates="branches")
    practitioner_links: Mapped[list[PractitionerBranch]] = relationship(
        back_populates="branch", cascade="all, delete-orphan"
    )
    schedules: Mapped[list[PractitionerSchedule]] = relationship(
        back_populates="branch", cascade="all, delete-orphan"
    )
    appointments: Mapped[list[Appointment]] = relationship(back_populates="branch")

    def __repr__(self) -> str:
        return f"<Branch id={self.id} name={self.name!r}>"
