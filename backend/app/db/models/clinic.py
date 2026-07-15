from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.branch import Branch
    from app.db.models.department import Department


class Clinic(UUIDPkMixin, TimestampMixin, Base):
    """The top-level tenant. Everything else (branches, departments,
    practitioners transitively) hangs off exactly one clinic -- this
    project models a single clinic operator with multiple locations,
    not a multi-tenant SaaS with many unrelated clinics.
    """

    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Kolkata"
    )
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )

    branches: Mapped[list[Branch]] = relationship(
        back_populates="clinic", cascade="all, delete-orphan"
    )
    departments: Mapped[list[Department]] = relationship(
        back_populates="clinic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Clinic id={self.id} name={self.name!r}>"
