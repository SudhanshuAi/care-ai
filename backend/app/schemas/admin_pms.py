"""Schemas for the mock-PMS admin console."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PmsReceiptSummary(BaseModel):
    id: UUID
    appointment_id: UUID
    operation: str
    idempotency_key: str
    payload: dict[str, Any]
    received_at: datetime


class AppointmentAdminSummary(BaseModel):
    appointment_id: UUID
    status: str
    patient_id: UUID
    patient_name: str
    patient_phone: str
    practitioner_id: UUID
    practitioner_name: str
    branch_id: UUID
    branch_name: str
    appointment_type_id: UUID
    appointment_type_name: str
    start_time: datetime
    end_time: datetime
    pms_sync_status: str
    pms_sync_operation: str | None = None
    pms_sync_attempts: int = 0
    pms_last_attempt_at: datetime | None = None
    pms_synced_at: datetime | None = None
    pms_last_error: str | None = None
    receipt_count: int = 0
    created_at: datetime


class AppointmentAdminDetail(AppointmentAdminSummary):
    notes: str | None = None
    receipts: list[PmsReceiptSummary] = Field(default_factory=list)


class AppointmentAdminListResponse(BaseModel):
    total: int
    items: list[AppointmentAdminSummary]


class PmsReceiptListResponse(BaseModel):
    total: int
    items: list[PmsReceiptSummary]


class PmsRetryResponse(BaseModel):
    appointment_id: UUID
    operation: str
    status: str
    attempted: bool
    detail: str | None = None
