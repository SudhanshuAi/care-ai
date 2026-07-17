"""Application entrypoint.

Builds and configures the FastAPI application: logging, middleware,
routers, and lifespan (startup/shutdown) hooks. Business/domain routers
(tools, webhooks, admin) are added here in later milestones -- this
file intentionally only wires infrastructure for now.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.prometheus_metrics import router as prometheus_router
from app.api.tools import router as tools_router
from app.api.webhooks_bolna import router as bolna_webhook_router
from app.api.webhooks_retell import router as retell_webhook_router
from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging, get_logger
from app.core.metrics import record_booking_failure
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

    cors_origins = settings.cors_origin_list
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        # Render's platform health check defaults to "/". Without this,
        # it 404s every check (visible as noisy request logs, and on some
        # plans can be mistaken for an unhealthy instance) even though the
        # app is otherwise fine. Kept dependency-free/instant so it never
        # itself becomes the slow part of a cold start.
        return {"status": "ok", "service": settings.app_name}

    app.include_router(health_router)
    app.include_router(tools_router)
    app.include_router(retell_webhook_router)
    app.include_router(bolna_webhook_router)
    app.include_router(admin_router)
    app.include_router(prometheus_router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        # The scheduling constraint is deliberately database-enforced;
        # surface a race/conflict as a useful tool response rather than
        # a generic 500 if a concurrent writer gets there first.
        if "uq_appointment_patient_no_overlap" in str(exc.orig):
            if "/create_appointment" in request.url.path:
                await record_booking_failure(detail="patient_double_booking")
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        "This patient already has a booked appointment that "
                        "overlaps this time. Cancel or reschedule the "
                        "existing appointment before booking another one."
                    ),
                    "code": "patient_double_booking",
                },
            )
        if "uq_appointment_no_overlap" in str(exc.orig):
            if "/create_appointment" in request.url.path:
                await record_booking_failure(detail="appointment_conflict")
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "The requested slot was just taken. Search live availability again.",
                    "code": "appointment_conflict",
                },
            )
        return JSONResponse(
            status_code=409,
            content={
                "detail": "The request conflicts with existing data.",
                "code": "integrity_conflict",
            },
        )

    return app


app = create_app()
