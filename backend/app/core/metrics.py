"""In-process Prometheus metrics and fire-and-forget PostgreSQL recording.

HTTP middleware, tool dispatchers, and appointment services call into
this module. Recording never raises into request handlers: a metrics
failure must not break booking or voice tools.
"""

from __future__ import annotations

import re
import time
from typing import Any

import structlog
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from app.db.models.metric_event import MetricEvent
from app.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

REGISTRY = CollectorRegistry()

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

HTTP_REQUESTS = Counter(
    "careai_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "careai_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "status"],
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
TOOL_INVOCATIONS = Counter(
    "careai_tool_invocations_total",
    "Voice/tool adapter invocations",
    ["tool", "ok"],
    registry=REGISTRY,
)
TOOL_LATENCY = Histogram(
    "careai_tool_latency_seconds",
    "Tool invocation latency in seconds",
    ["tool"],
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
LLM_LATENCY = Histogram(
    "careai_llm_latency_seconds",
    "LLM time-to-first-token / completion latency in seconds",
    ["source"],
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)
CALL_DURATION = Histogram(
    "careai_call_duration_seconds",
    "Completed or disconnected call duration in seconds",
    ["status"],
    registry=REGISTRY,
    buckets=(5, 15, 30, 60, 120, 300, 600, 1200),
)
BOOKINGS = Counter(
    "careai_bookings_total",
    "Appointment create outcomes",
    ["result"],
    registry=REGISTRY,
)
CANCELS = Counter(
    "careai_cancels_total",
    "Appointment cancel outcomes",
    ["result"],
    registry=REGISTRY,
)
RESCHEDULES = Counter(
    "careai_reschedules_total",
    "Appointment reschedule outcomes",
    ["result"],
    registry=REGISTRY,
)
LANGUAGES = Counter(
    "careai_language_total",
    "Observed call languages",
    ["language"],
    registry=REGISTRY,
)
INTERRUPTIONS = Counter(
    "careai_interruptions_total",
    "Calls marked disconnected / interrupted",
    registry=REGISTRY,
)
TOOL_RETRIES = Counter(
    "careai_tool_retries_total",
    "Idempotent tool / booking retries",
    ["operation"],
    registry=REGISTRY,
)


def normalize_path(path: str) -> str:
    """Collapse UUIDs and call ids so Prometheus labels stay low-cardinality."""

    path = _UUID_RE.sub("{id}", path)
    if path.startswith("/webhooks/retell/call-context/"):
        return "/webhooks/retell/call-context/{call_id}"
    return path


def prometheus_payload() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


async def record_event(
    *,
    name: str,
    value: float = 1.0,
    duration_ms: float | None = None,
    labels: dict[str, Any] | None = None,
    call_id: str | None = None,
    request_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Persist one metric event. Never raises to callers."""

    session = AsyncSessionLocal()
    try:
        session.add(
            MetricEvent(
                name=name,
                value=value,
                duration_ms=duration_ms,
                labels=labels or {},
                call_id=call_id,
                request_id=request_id,
                detail=detail,
            )
        )
        await session.commit()
    except Exception:
        logger.warning("metric_event_persist_failed", name=name, exc_info=True)
        try:
            await session.rollback()
        except Exception:
            pass
    finally:
        try:
            await session.close()
        except Exception:
            pass


async def record_endpoint_latency(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    request_id: str | None = None,
) -> None:
    path_label = normalize_path(path)
    status = str(status_code)
    HTTP_REQUESTS.labels(method=method, path=path_label, status=status).inc()
    HTTP_DURATION.labels(method=method, path=path_label, status=status).observe(
        duration_ms / 1000.0
    )
    await record_event(
        name="endpoint_latency",
        value=1.0,
        duration_ms=duration_ms,
        labels={"method": method, "path": path_label, "status": status},
        request_id=request_id,
    )


async def record_tool_latency(
    *,
    tool: str,
    ok: bool,
    duration_ms: float,
    call_id: str | None = None,
    request_id: str | None = None,
) -> None:
    TOOL_INVOCATIONS.labels(tool=tool, ok=str(ok).lower()).inc()
    TOOL_LATENCY.labels(tool=tool).observe(duration_ms / 1000.0)
    await record_event(
        name="tool_latency",
        value=1.0,
        duration_ms=duration_ms,
        labels={"tool": tool, "ok": ok},
        call_id=call_id,
        request_id=request_id,
    )


async def record_llm_latency(
    *,
    duration_ms: float,
    source: str = "orchestrator",
    call_id: str | None = None,
) -> None:
    LLM_LATENCY.labels(source=source).observe(duration_ms / 1000.0)
    await record_event(
        name="llm_latency",
        value=1.0,
        duration_ms=duration_ms,
        labels={"source": source},
        call_id=call_id,
    )


async def record_call_duration(
    *,
    duration_ms: float,
    status: str,
    call_id: str | None = None,
    language: str | None = None,
) -> None:
    CALL_DURATION.labels(status=status).observe(duration_ms / 1000.0)
    labels: dict[str, Any] = {"status": status}
    if language:
        labels["language"] = language
    await record_event(
        name="call_duration",
        value=1.0,
        duration_ms=duration_ms,
        labels=labels,
        call_id=call_id,
    )


async def record_booking_success(*, call_id: str | None = None, replay: bool = False) -> None:
    BOOKINGS.labels(result="success").inc()
    await record_event(
        name="booking_success",
        labels={"replay": replay},
        call_id=call_id,
    )
    if replay:
        await record_tool_retry(operation="create_appointment", call_id=call_id)


async def record_booking_failure(*, detail: str | None = None, call_id: str | None = None) -> None:
    BOOKINGS.labels(result="failure").inc()
    await record_event(name="booking_failure", call_id=call_id, detail=detail)


async def record_cancel_success(*, call_id: str | None = None, replay: bool = False) -> None:
    CANCELS.labels(result="success").inc()
    await record_event(
        name="cancel_success",
        labels={"replay": replay},
        call_id=call_id,
    )
    if replay:
        await record_tool_retry(operation="cancel_appointment", call_id=call_id)


async def record_reschedule_success(*, call_id: str | None = None, replay: bool = False) -> None:
    RESCHEDULES.labels(result="success").inc()
    await record_event(
        name="reschedule_success",
        labels={"replay": replay},
        call_id=call_id,
    )
    if replay:
        await record_tool_retry(operation="reschedule_appointment", call_id=call_id)


async def record_language(*, language: str, call_id: str | None = None) -> None:
    normalized = (language or "unknown").strip() or "unknown"
    LANGUAGES.labels(language=normalized).inc()
    await record_event(
        name="language",
        labels={"language": normalized},
        call_id=call_id,
    )


async def record_interruption(*, call_id: str | None = None) -> None:
    INTERRUPTIONS.inc()
    await record_event(name="interruption", call_id=call_id)


async def record_tool_retry(*, operation: str, call_id: str | None = None) -> None:
    TOOL_RETRIES.labels(operation=operation).inc()
    await record_event(
        name="tool_retry",
        labels={"operation": operation},
        call_id=call_id,
    )


class Timer:
    """Simple wall-clock timer for tool / LLM spans."""

    def __init__(self) -> None:
        self._started = time.perf_counter()

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self._started) * 1000, 2)
