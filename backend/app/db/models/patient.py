from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment import Appointment
    from app.db.models.call import Call
    from app.db.models.followup import FollowUp


class Patient(UUIDPkMixin, TimestampMixin, Base):
    """A patient record.

    `phone` is deliberately NOT unique. The assignment explicitly
    requires supporting a shared family line -- two different patients
    with the same phone number -- and disambiguating by asking for the
    caller's name, not by assuming a 1:1 phone-to-patient mapping.
    Lookups by phone are expected to return zero, one, or many rows;
    the tool-calling layer (added in a later milestone) is what turns
    "many" into a disambiguation prompt.
    """

    __tablename__ = "patients"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    date_of_birth: Mapped[dt.date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    appointments: Mapped[list[Appointment]] = relationship(back_populates="patient")
    calls: Mapped[list[Call]] = relationship(
        back_populates="patient", foreign_keys="Call.patient_id"
    )
    followups: Mapped[list[FollowUp]] = relationship(back_populates="patient")

    def __repr__(self) -> str:
        return f"<Patient id={self.id} full_name={self.full_name!r}>"
