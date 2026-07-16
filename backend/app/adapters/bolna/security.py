"""Bolna webhook authenticity checks.

Bolna Custom Functions send `Authorization: Bearer <token>` when
`api_token` is set on the tool. We compare that bearer value against
`BOLNA_API_TOKEN` (with or without a leading `Bearer ` prefix).
"""

from __future__ import annotations

import hmac

from app.core.exceptions import ValidationError


def verify_bolna_bearer(
    *,
    authorization_header: str | None,
    api_token: str,
) -> None:
    if not authorization_header:
        raise ValidationError("Missing Authorization header.")

    expected = api_token.strip()
    if expected.lower().startswith("bearer "):
        expected = expected[7:].strip()

    provided = authorization_header.strip()
    if provided.lower().startswith("bearer "):
        provided = provided[7:].strip()

    if not provided or not hmac.compare_digest(provided, expected):
        raise ValidationError("Invalid Bolna Authorization bearer token.")
