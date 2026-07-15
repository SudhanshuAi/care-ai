from app.adapters.retell.security import verify_retell_signature
from app.core.exceptions import ValidationError

import hashlib
import hmac
import time

import pytest


def _sign(raw_body: bytes, api_key: str, timestamp_ms: int | None = None) -> str:
    timestamp_ms = timestamp_ms or int(time.time() * 1000)
    digest = hmac.new(
        api_key.encode("utf-8"),
        raw_body + str(timestamp_ms).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"v={timestamp_ms},d={digest}"


def test_valid_signature_passes() -> None:
    body = b'{"name":"lookup_patient","args":{}}'
    api_key = "test_key"
    verify_retell_signature(
        raw_body=body,
        signature_header=_sign(body, api_key),
        api_key=api_key,
    )


def test_invalid_signature_raises() -> None:
    body = b'{"name":"lookup_patient","args":{}}'
    with pytest.raises(ValidationError, match="Invalid X-Retell-Signature"):
        verify_retell_signature(
            raw_body=body,
            signature_header=_sign(body, "other_key"),
            api_key="test_key",
        )


def test_missing_signature_raises() -> None:
    with pytest.raises(ValidationError, match="Missing"):
        verify_retell_signature(raw_body=b"{}", signature_header=None, api_key="k")
