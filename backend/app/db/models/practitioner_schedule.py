from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Time
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import Weekday
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.branch import Branch
    from app.db.models.practitioner import Practitioner


class PractitionerSchedule(UUIDPkMixin, TimestampMixin, Base):
    """One recurring weekly working-hours block for a practitioner at a
    specific branch (a doctor with morning-only hours at one branch and
    a full day at another gets two rows, not one).

    `start_time`/`end_time` are stored as local wall-clock `Time`
    values (no UTC offset) -- interpreted using the parent `Branch`'s
    `timezone`, not converted to UTC at write time. Storing wall time
    is deliberate: "9am-1pm every Monday" should mean 9am-1pm in that
    branch's local time even across a DST transition, which a
    pre-converted UTC instant would get wrong twice a year.
    `valid_from`/`valid_to` allow temporary hour changes (e.g. a
    holiday-season schedule) without deleting the standing one.
    """

    __tablename__ = "practitioner_schedules"

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
    weekday: Mapped[Weekday] = mapped_column(
        SAEnum(
            Weekday,
            name="weekday",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    practitioner: Mapped[Practitioner] = relationship(back_populates="schedules")
    branch: Mapped[Branch] = relationship(back_populates="schedules")

    def __repr__(self) -> str:
        return (
            f"<PractitionerSchedule practitioner_id={self.practitioner_id} "
            f"weekday={self.weekday} {self.start_time}-{self.end_time}>"
        )
