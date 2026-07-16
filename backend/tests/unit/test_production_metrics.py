"""Unit tests for production metrics helpers."""

from app.core.metrics import HTTP_REQUESTS, normalize_path, prometheus_payload


def test_normalize_path_collapses_uuids_and_call_context() -> None:
    assert (
        normalize_path("/tools/appointments/520a8031-afbe-40c5-88a4-c70f605eb522/cancel")
        == "/tools/appointments/{id}/cancel"
    )
    assert (
        normalize_path("/webhooks/retell/call-context/retell-abc-123")
        == "/webhooks/retell/call-context/{call_id}"
    )


def test_prometheus_payload_is_text_exposition() -> None:
    HTTP_REQUESTS.labels(method="GET", path="/health/live", status="200").inc()
    body, content_type = prometheus_payload()
    assert b"careai_http_requests_total" in body
    assert "text/plain" in content_type or "openmetrics" in content_type
