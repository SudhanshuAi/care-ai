"""Provider-agnostic PMS write-back contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.db.models.appointment import Appointment


class PmsWritebackError(Exception):
    """A retryable or terminal downstream PMS write-back failure."""


@dataclass(frozen=True)
class PmsWritebackResult:
    provider: str
    external_reference: str
    replayed: bool = False


class PmsAdapter(Protocol):
    async def write_appointment(
        self, appointment: Appointment, *, idempotency_key: str
    ) -> PmsWritebackResult:
        """Persist the appointment in the downstream PMS."""
