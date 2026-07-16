"""Structured logging setup.

Uses `structlog` layered on top of the stdlib `logging` module so that:
  * every log line (ours and third-party, e.g. uvicorn) is a single
    structured event,
  * output is human-readable in local/dev and JSON when `JSON_LOGS=true`,
  * request and conversation context (`request_id`, `call_id`,
    `conversation_id`, `patient_id`, …) merge automatically via
    contextvars — see `app.core.observability`.
"""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure stdlib logging + structlog for the whole process.

    Call this once, as early as possible (before the FastAPI app is
    created), so that any import-time logging is also captured correctly.

    Production deployments should set ``JSON_LOGS=true`` so log aggregators
    receive one JSON object per line.
    """

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level.upper())

    # Route uvicorn's own loggers through the same handler/formatter so
    # access logs and app logs look consistent instead of two formats
    # interleaved on stdout.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to `name` (typically `__name__`)."""

    return structlog.get_logger(name)
