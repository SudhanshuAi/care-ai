"""Retell webhook authenticity checks.

Retell signs requests with HMAC-SHA256 over `raw_body + timestamp`
using the API key that has the webhook badge. See:
https://docs.retellai.com/features/secure-webhook
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time

from app.core.exceptions import ValidationError

_SIGNATURE_RE = re.compile(r"v=(\d+),d=([0-9a-fA-F]+)")
_MAX_SKEW_MS = 5 * 60 * 1000


def verify_retell_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    api_key: str,
) -> None:
    if not signature_header:
        raise ValidationError("Missing X-Retell-Signature header.")

    match = _SIGNATURE_RE.fullmatch(signature_header.strip())
    if match is None:
        raise ValidationError("Malformed X-Retell-Signature header.")

    timestamp_ms = int(match.group(1))
    digest = match.group(2).lower()
    now_ms = int(time.time() * 1000)
    if abs(now_ms - timestamp_ms) > _MAX_SKEW_MS:
        raise ValidationError("X-Retell-Signature timestamp is outside the allowed window.")

    expected = hmac.new(
        api_key.encode("utf-8"),
        raw_body + str(timestamp_ms).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, digest):
        raise ValidationError("Invalid X-Retell-Signature.")
