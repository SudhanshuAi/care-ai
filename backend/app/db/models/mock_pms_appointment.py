"""Durable mock-PMS receipt for an appointment write-back.

The mock provider intentionally persists a compact representation separate
from Care AI's appointment row. This makes the write-back observable and
idempotent today while keeping the adapter boundary suitable for a real PMS
later.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import UUIDPkMixin


class MockPmsAppointment(UUIDPkMixin, Base):
    __tablename__ = "mock_pms_appointments"
    __table_args__ = (
        Index("ix_mock_pms_appointments_appointment_id", "appointment_id"),
        Index("ix_mock_pms_appointments_idempotency_key", "idempotency_key"),
    )

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MockPmsAppointment appointment_id={self.appointment_id}>"
