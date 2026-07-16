"""Append-only production metric events persisted in PostgreSQL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import UUIDPkMixin


class MetricEvent(UUIDPkMixin, Base):
    """One recorded metric sample.

    Events are intentionally append-only and denormalized so the admin
    dashboard and Prometheus scrape path can aggregate without joining
    operational booking tables on every request.
    """

    __tablename__ = "metric_events"
    __table_args__ = (
        Index("ix_metric_events_name_occurred_at", "name", "occurred_at"),
        Index("ix_metric_events_occurred_at", "occurred_at"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    labels: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    call_id: Mapped[str | None] = mapped_column(String(128), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<MetricEvent name={self.name!r} value={self.value}>"
