"""Admin metrics and mock-PMS operational console endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.admin_pms import (
    AppointmentAdminDetail,
    AppointmentAdminListResponse,
    PmsReceiptListResponse,
    PmsRetryResponse,
)
from app.services.admin_pms_service import AdminPmsService
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


def admin_pms_service(db: DbSession) -> AdminPmsService:
    return AdminPmsService(db)


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


@router.get(
    "/pms/appointments",
    response_model=AppointmentAdminListResponse,
    summary="List appointments with mock-PMS sync status",
)
async def list_pms_appointments(
    service: Annotated[AdminPmsService, Depends(admin_pms_service)],
    status: Annotated[str | None, Query()] = None,
    pms_sync_status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AppointmentAdminListResponse:
    return await service.list_appointments(
        status=status,
        pms_sync_status=pms_sync_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/pms/appointments/{appointment_id}",
    response_model=AppointmentAdminDetail,
    summary="Appointment detail with mock-PMS receipt timeline",
)
async def get_pms_appointment(
    appointment_id: UUID,
    service: Annotated[AdminPmsService, Depends(admin_pms_service)],
) -> AppointmentAdminDetail:
    return await service.appointment_detail(appointment_id)


@router.get(
    "/pms/receipts",
    response_model=PmsReceiptListResponse,
    summary="List mock-PMS write-back receipts",
)
async def list_pms_receipts(
    service: Annotated[AdminPmsService, Depends(admin_pms_service)],
    operation: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PmsReceiptListResponse:
    return await service.list_receipts(
        operation=operation,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/pms/appointments/{appointment_id}/retry",
    response_model=PmsRetryResponse,
    summary="Retry the latest pending mock-PMS write-back for an appointment",
)
async def retry_pms_appointment(
    appointment_id: UUID,
    service: Annotated[AdminPmsService, Depends(admin_pms_service)],
) -> PmsRetryResponse:
    return await service.retry_appointment(appointment_id)
