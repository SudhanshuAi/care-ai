"""Read models and retry actions for the mock-PMS admin console."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.appointment import Appointment
from app.db.models.enums import AppointmentStatus, PmsSyncStatus
from app.db.models.mock_pms_appointment import MockPmsAppointment
from app.repositories.pms_repository import PmsRepository
from app.schemas.admin_pms import (
    AppointmentAdminDetail,
    AppointmentAdminListResponse,
    AppointmentAdminSummary,
    PmsReceiptListResponse,
    PmsReceiptSummary,
    PmsRetryResponse,
)
from app.services.pms_sync_service import PmsSyncService


class AdminPmsService:
    def __init__(
        self,
        session: AsyncSession,
        repository: PmsRepository | None = None,
        pms_sync: PmsSyncService | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or PmsRepository(session)
        self._pms_sync = pms_sync or PmsSyncService()

    async def list_appointments(
        self,
        *,
        status: str | None = None,
        pms_sync_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AppointmentAdminListResponse:
        appointments, total = await self._repository.list_appointments(
            status=self._parse_appointment_status(status),
            pms_sync_status=self._parse_pms_status(pms_sync_status),
            limit=limit,
            offset=offset,
        )
        counts = await self._repository.receipt_counts(
            [appointment.id for appointment in appointments]
        )
        return AppointmentAdminListResponse(
            total=total,
            items=[
                self._summary(appointment, counts.get(appointment.id, 0))
                for appointment in appointments
            ],
        )

    async def appointment_detail(
        self, appointment_id: UUID
    ) -> AppointmentAdminDetail:
        appointment = await self._repository.appointment_detail(appointment_id)
        if appointment is None:
            raise NotFoundError("Appointment was not found.")
        receipts = await self._repository.receipts_for_appointment(appointment_id)
        summary = self._summary(appointment, len(receipts))
        return AppointmentAdminDetail(
            **summary.model_dump(),
            notes=appointment.notes,
            receipts=[self._receipt(receipt) for receipt in receipts],
        )

    async def list_receipts(
        self,
        *,
        operation: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PmsReceiptListResponse:
        if operation and operation not in {"create", "reschedule", "cancel"}:
            raise ValidationError(
                "operation must be one of: create, reschedule, cancel."
            )
        receipts, total = await self._repository.list_receipts(
            operation=operation,
            limit=limit,
            offset=offset,
        )
        return PmsReceiptListResponse(
            total=total,
            items=[self._receipt(receipt) for receipt in receipts],
        )

    async def retry_appointment(self, appointment_id: UUID) -> PmsRetryResponse:
        appointment = await self._repository.appointment_detail(appointment_id)
        if appointment is None:
            raise NotFoundError("Appointment was not found.")
        operation = appointment.pms_sync_operation or "create"
        result = await self._pms_sync.sync_appointment(
            appointment_id, operation=operation
        )
        return PmsRetryResponse(
            appointment_id=result.appointment_id,
            operation=operation,
            status=result.status.value,
            attempted=result.attempted,
            detail=result.detail,
        )

    @staticmethod
    def _summary(appointment: Appointment, receipt_count: int) -> AppointmentAdminSummary:
        return AppointmentAdminSummary(
            appointment_id=appointment.id,
            status=appointment.status.value,
            patient_id=appointment.patient_id,
            patient_name=appointment.patient.full_name,
            patient_phone=appointment.patient.phone,
            practitioner_id=appointment.practitioner_id,
            practitioner_name=appointment.practitioner.display_name,
            branch_id=appointment.branch_id,
            branch_name=appointment.branch.name,
            appointment_type_id=appointment.appointment_type_id,
            appointment_type_name=appointment.appointment_type.name,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            pms_sync_status=appointment.pms_sync_status.value,
            pms_sync_operation=appointment.pms_sync_operation,
            pms_sync_attempts=appointment.pms_sync_attempts,
            pms_last_attempt_at=appointment.pms_last_attempt_at,
            pms_synced_at=appointment.pms_synced_at,
            pms_last_error=appointment.pms_last_error,
            receipt_count=receipt_count,
            created_at=appointment.created_at,
        )

    @staticmethod
    def _receipt(receipt: MockPmsAppointment) -> PmsReceiptSummary:
        return PmsReceiptSummary(
            id=receipt.id,
            appointment_id=receipt.appointment_id,
            operation=receipt.operation,
            idempotency_key=receipt.idempotency_key,
            payload=receipt.payload,
            received_at=receipt.received_at,
        )

    @staticmethod
    def _parse_appointment_status(value: str | None) -> AppointmentStatus | None:
        if value is None or value == "":
            return None
        try:
            return AppointmentStatus(value)
        except ValueError as exc:
            raise ValidationError(
                "status must be one of: booked, rescheduled, cancelled, completed, no_show."
            ) from exc

    @staticmethod
    def _parse_pms_status(value: str | None) -> PmsSyncStatus | None:
        if value is None or value == "":
            return None
        try:
            return PmsSyncStatus(value)
        except ValueError as exc:
            raise ValidationError(
                "pms_sync_status must be one of: pending, synced, failed, pending_retry."
            ) from exc
