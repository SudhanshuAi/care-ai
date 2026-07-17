from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import IdempotencyOperationType
from app.db.models.mixins import TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.appointment import Appointment


class IdempotencyKey(UUIDPkMixin, TimestampMixin, Base):
    """Guards every mutating tool call (create/reschedule/cancel
    appointment, PMS write-back) against duplicate execution.

    The caller (our own LLM orchestrator) generates `key` once per
    logical operation and resends the same value on retry (e.g. after a
    timeout where it can't tell if the first attempt landed). On a
    retry with a `key` already present here, the handler returns
    `response_snapshot` unchanged instead of re-executing the
    operation -- this is the defined, testable behavior behind "a
    defined behavior when that call fails."
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    operation_type: Mapped[IdempotencyOperationType] = mapped_column(
        SAEnum(
            IdempotencyOperationType,
            name="idempotency_operation_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL")
    )
    request_hash: Mapped[str | None] = mapped_column(String(64))
    response_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    appointment: Mapped[Appointment | None] = relationship()

    def __repr__(self) -> str:
        return f"<IdempotencyKey key={self.key!r} operation_type={self.operation_type}>"
