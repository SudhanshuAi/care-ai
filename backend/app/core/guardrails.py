"""Deterministic backend guardrails for voice/tool booking flows.

Prompt instructions are advisory only. These helpers encode the hard
business rules that must hold even when the LLM hallucinates IDs,
skips a live search, or invents an immediate human transfer.
"""

from __future__ import annotations

import re
from datetime import timedelta

# Offered slots expire quickly so an agent cannot confirm from memory.
AVAILABILITY_OFFER_TTL = timedelta(minutes=3)

CALLBACK_EXPECTATION = (
    "A human team member will call the patient back. "
    "Do not imply an immediate live transfer."
)

_IMMEDIATE_TRANSFER_RE = re.compile(
    r"("
    r"transfer(ring)?\s+(you\s+)?(now|immediately|right\s+away)|"
    r"connect(ing)?\s+(you\s+)?(now|immediately|to\s+a\s+(live\s+)?(agent|human|person))|"
    r"speaking\s+(to|with)\s+(a\s+)?(live\s+)?(agent|human|person)\s+now|"
    r"hold\s+(on|the\s+line).{0,40}(transfer|connect)"
    r")",
    re.IGNORECASE,
)


def require_caller_full_name(value: str | None) -> str:
    name = (value or "").strip()
    if not name:
        raise_validation(
            "caller_full_name is required; anonymous bookings are not allowed."
        )
    return name


def notes_promise_immediate_transfer(notes: str) -> bool:
    return bool(_IMMEDIATE_TRANSFER_RE.search(notes or ""))


def raise_validation(detail: str) -> None:
    from app.core.exceptions import ValidationError

    raise ValidationError(detail)
