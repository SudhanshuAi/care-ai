from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.db.base import Base
from app.db.models.enums import AppointmentStatus, PmsSyncStatus
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment_type import AppointmentType
    from app.db.models.branch import Branch
    from app.db.models.call import Call
    from app.db.models.patient import Patient
    from app.db.models.practitioner import Practitioner


class Appointment(UUIDPkMixin, TimestampMixin, Base):
    """A booked slot.

    Double-booking is prevented at the database layer, not only in
    application code: `uq_appointment_no_overlap` is a PostgreSQL
    `EXCLUDE` constraint (enabled by the `btree_gist` extension, added
    in the initial migration) that rejects any INSERT/UPDATE creating
    two rows with `status = 'booked'` for the same practitioner whose
    `[start_time, end_time)` ranges overlap (`tstzrange`, since these
    columns are timezone-aware `timestamptz`). This holds under real
    concurrency -- two simultaneous booking attempts for the same slot
    will have one succeed and one fail at the database level -- which a
    purely application-level "check then insert" cannot guarantee.

    `uq_appointment_patient_no_overlap` is the same idea scoped to
    `patient_id` instead of `practitioner_id`: it stops the *same
    patient* from ending up with two BOOKED appointments (with two
    different practitioners/branches) at overlapping times. Without it,
    nothing at the DB layer stops a patient from being "double booked"
    -- the application-level check in `AppointmentService` is the first
    line of defense, but this constraint is what makes it safe under
    concurrency too.

    `pms_sync_status` tracks the mock-PMS write-back outcome
    separately from the booking itself: the appointment is confirmed to
    the caller once *this* row commits, regardless of whether the
    downstream PMS write-back has succeeded yet.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        ExcludeConstraint(
            ("practitioner_id", "="),
            (text("tstzrange(start_time, end_time, '[)')"), "&&"),
            name="uq_appointment_no_overlap",
            using="gist",
            where=text("status = 'booked'"),
        ),
        ExcludeConstraint(
            ("patient_id", "="),
            (text("tstzrange(start_time, end_time, '[)')"), "&&"),
            name="uq_appointment_patient_no_overlap",
            using="gist",
            where=text("status = 'booked'"),
        ),
        Index("ix_appointments_practitioner_start", "practitioner_id", "start_time"),
        Index("ix_appointments_branch_start", "branch_id", "start_time"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("practitioners.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )
    appointment_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("appointment_types.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_call_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL")
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            AppointmentStatus,
            name="appointment_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=AppointmentStatus.BOOKED,
    )
    pms_sync_status: Mapped[PmsSyncStatus] = mapped_column(
        SAEnum(
            PmsSyncStatus,
            name="pms_sync_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PmsSyncStatus.PENDING,
    )
    pms_sync_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pms_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    pms_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pms_last_error: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    patient: Mapped[Patient] = relationship(back_populates="appointments")
    practitioner: Mapped[Practitioner] = relationship(back_populates="appointments")
    branch: Mapped[Branch] = relationship(back_populates="appointments")
    appointment_type: Mapped[AppointmentType] = relationship(back_populates="appointments")
    created_by_call: Mapped[Call | None] = relationship(
        back_populates="appointments_created", foreign_keys=[created_by_call_id]
    )

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} start_time={self.start_time} status={self.status}>"
