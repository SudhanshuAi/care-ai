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
    from app.db.models.department import Department
    from app.db.models.practitioner_branch import PractitionerBranch
    from app.db.models.practitioner_schedule import PractitionerSchedule


class Practitioner(UUIDPkMixin, TimestampMixin, Base):
    """A doctor/therapist. `clinic_id` is a direct FK even though it is
    technically derivable via `department.clinic_id` -- this
    intentional denormalization keeps "all practitioners at this
    clinic" a single indexed filter instead of a join through
    departments, which matters for the earliest-slot-across-branches
    search described in the implementation plan.
    """

    __tablename__ = "practitioners"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(64))

    clinic: Mapped[Clinic] = relationship()
    department: Mapped[Department] = relationship(back_populates="practitioners")
    branch_links: Mapped[list[PractitionerBranch]] = relationship(
        back_populates="practitioner", cascade="all, delete-orphan"
    )
    schedules: Mapped[list[PractitionerSchedule]] = relationship(
        back_populates="practitioner", cascade="all, delete-orphan"
    )
    appointments: Mapped[list[Appointment]] = relationship(back_populates="practitioner")

    def __repr__(self) -> str:
        return f"<Practitioner id={self.id} display_name={self.display_name!r}>"
