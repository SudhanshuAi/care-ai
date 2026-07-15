from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.branch import Branch
    from app.db.models.practitioner import Practitioner


class PractitionerBranch(UUIDPkMixin, TimestampMixin, Base):
    """Which branches a practitioner sees patients at (many-to-many).

    Modeled as an explicit entity rather than a plain `secondary=`
    association table so it can carry its own attributes (`is_primary`
    today; things like a per-branch consultation fee override would
    slot in here later) without a migration to promote a secondary
    table into a first-class one.
    """

    __tablename__ = "practitioner_branches"
    __table_args__ = (
        UniqueConstraint("practitioner_id", "branch_id", name="uq_practitioner_branch"),
    )

    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    practitioner: Mapped[Practitioner] = relationship(back_populates="branch_links")
    branch: Mapped[Branch] = relationship(back_populates="practitioner_links")

    def __repr__(self) -> str:
        return (
            f"<PractitionerBranch practitioner_id={self.practitioner_id} "
            f"branch_id={self.branch_id}>"
        )
