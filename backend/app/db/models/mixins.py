"""Shared columns every model gets, factored out so each model file only
declares what makes it distinct.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPkMixin:
    """Surrogate UUID primary key, generated application-side.

    Generating the UUID in Python (`default=uuid.uuid4`) rather than
    relying on a Postgres default means new instances have a usable
    `.id` immediately after construction, before the row is even
    flushed -- useful for wiring up relationships in the same unit of
    work (e.g. the seed script) without an extra round trip.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """`created_at` / `updated_at`, both timezone-aware and DB-assigned.

    Using `server_default=func.now()` (rather than a Python-side
    default) means the timestamp is assigned by Postgres at insert
    time, which is consistent even if application server clocks drift,
    and `onupdate=func.now()` keeps `updated_at` correct without every
    write path having to remember to set it.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
