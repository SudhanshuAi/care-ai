"""Application entrypoint.

Builds and configures the FastAPI application: logging, middleware,
routers, and lifespan (startup/shutdown) hooks. Business/domain routers
(tools, webhooks, admin) are added here in later milestones -- this
file intentionally only wires infrastructure for now.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.health import router as health_router
from app.api.tools import router as tools_router
from app.api.webhooks_bolna import router as bolna_webhook_router
from app.api.webhooks_retell import router as retell_webhook_router
from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware
from app.db.session import dispose_engine

settings = get_settings()
configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        env=settings.env,
    )
    yield
    logger.info("application_shutdown")
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(tools_router)
    app.include_router(retell_webhook_router)
    app.include_router(bolna_webhook_router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        # The scheduling constraint is deliberately database-enforced;
        # surface a race/conflict as a useful tool response rather than
        # a generic 500 if a concurrent writer gets there first.
        if "uq_appointment_no_overlap" in str(exc.orig):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "The requested slot was just taken. Search live availability again.",
                    "code": "appointment_conflict",
                },
            )
        return JSONResponse(
            status_code=409,
            content={"detail": "The request conflicts with existing data.", "code": "integrity_conflict"},
        )

    return app


app = create_app()
