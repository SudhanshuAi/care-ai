from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment_type import AppointmentType
    from app.db.models.clinic import Clinic
    from app.db.models.practitioner import Practitioner


class Department(UUIDPkMixin, TimestampMixin, Base):
    """A specialty/service line within a clinic (e.g. Dentistry,
    Physiotherapy). Scoped to the clinic, not to a branch -- the same
    department can be offered at multiple branches, which is what makes
    "branch-specific triage" (asking for a specialty at a named branch)
    a filter on `Practitioner`/`PractitionerBranch`, not a separate
    per-branch department row.
    """

    __tablename__ = "departments"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    clinic: Mapped[Clinic] = relationship(back_populates="departments")
    practitioners: Mapped[list[Practitioner]] = relationship(back_populates="department")
    appointment_types: Mapped[list[AppointmentType]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name!r}>"
