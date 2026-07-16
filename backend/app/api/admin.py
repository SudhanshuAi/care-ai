"""Admin metrics and operational dashboard endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/metrics",
    summary="Aggregated production metrics from PostgreSQL",
)
async def admin_metrics(
    db: DbSession,
    hours: Annotated[
        int | None,
        Query(ge=1, le=24 * 30, description="Lookback window in hours; omit for all time."),
    ] = 24,
) -> dict[str, Any]:
    return await MetricsService(db).aggregated(hours=hours)


@router.get(
    "/dashboard",
    summary="Operational dashboard view of production metrics",
)
async def admin_dashboard(
    db: DbSession,
    hours: Annotated[
        int | None,
        Query(ge=1, le=24 * 30, description="Lookback window in hours; omit for all time."),
    ] = 24,
) -> dict[str, Any]:
    return await MetricsService(db).dashboard(hours=hours)
