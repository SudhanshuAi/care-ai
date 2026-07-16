"""HTTP middleware: per-request logging, correlation id, and endpoint metrics.

Every request gets a `request_id` (reused from the incoming
`X-Request-ID` header if the caller supplied one, e.g. a load balancer
or an upstream service). The id is bound into structlog's contextvars
for the duration of the request, so every log line emitted while
handling it -- from any module -- is automatically tagged with it, and
it is echoed back in the response header for client-side correlation.

Voice webhooks additionally bind `provider` (retell / bolna / rest).
Tool dispatchers bind `call_id` / `conversation_id` for conversation-wide
correlation across reconnects — see `app.core.observability`.

Endpoint latency is also recorded into the production metrics store
and Prometheus registry without changing response bodies.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.observability import bind_request_provider

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# High-cardinality / scrape endpoints that should not write a PG row
# on every hit (Prometheus scrape itself would create a feedback loop).
_SKIP_PERSIST_PREFIXES = ("/metrics", "/health/")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        bind_request_provider(request.url.path)

        started_at = time.perf_counter()
        response: Response | None = None
        exception_type: str | None = None
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            exception_type = type(exc).__name__
            raise
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            status_code = response.status_code if response is not None else 500
            if response is not None:
                response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                status="error" if status_code >= 500 or exception_type else "ok",
                latency_ms=duration_ms,
                duration_ms=duration_ms,
                exception_type=exception_type,
            )
            path = request.url.path
            if not any(path.startswith(prefix) for prefix in _SKIP_PERSIST_PREFIXES):
                # Import lazily so middleware remains importable before
                # the DB engine is configured in tests/scripts.
                from app.core.metrics import record_endpoint_latency

                await record_endpoint_latency(
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
