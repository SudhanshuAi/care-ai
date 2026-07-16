"""Transactional appointment lifecycle operations."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError, ValidationError
from app.core.guardrails import require_caller_full_name
from app.core.logging import get_logger
from app.core.metrics import (
    record_booking_failure,
    record_booking_success,
    record_cancel_success,
    record_reschedule_success,
)
from app.db.models import Appointment, IdempotencyKey
from app.db.models.availability_offer import AvailabilityOffer
from app.db.models.enums import (
    AppointmentStatus,
    IdempotencyOperationType,
    PmsSyncStatus,
)
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.availability_offer_repository import AvailabilityOfferRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.scheduling_repository import SchedulingRepository
from app.schemas.tools import (
    AppointmentConfirmation,
    CancelAppointmentRequest,
    CreateAppointmentRequest,
    FeeResult,
    RescheduleAppointmentRequest,
)
from app.services.availability_service import AvailabilityService
from app.services.pms_sync_service import PmsSyncService

logger = get_logger(__name__)


class AppointmentService:
    def __init__(
        self,
        session: AsyncSession,
        appointments: AppointmentRepository,
        patients: PatientRepository,
        scheduling: SchedulingRepository,
        offers: AvailabilityOfferRepository | None = None,
        pms_sync: PmsSyncService | None = None,
    ) -> None:
        self._session = session
        self._appointments = appointments
        self._patients = patients
        self._scheduling = scheduling
        self._offers = offers or AvailabilityOfferRepository(session)
        self._availability = AvailabilityService(scheduling, self._offers)
        self._pms_sync = pms_sync or PmsSyncService()

    async def create(
        self,
        request: CreateAppointmentRequest,
        idempotency_key: str,
        *,
        created_by_call_id: UUID | None = None,
    ) -> AppointmentConfirmation:
        request_hash = self._request_hash(request)
        try:
            async with self._session.begin():
                replay = await self._idempotent_replay(
                    idempotency_key,
                    IdempotencyOperationType.CREATE_APPOINTMENT,
                    request_hash,
                )
                if replay is not None:
                    response = replay
                else:
                    caller_name = require_caller_full_name(request.caller_full_name)
                    patient = await self._patients.by_id(request.patient_id)
                    if patient is None:
                        raise NotFoundError("Patient was not found.")
                    self._verify_caller_name(patient.full_name, caller_name)
                    await self._assert_booking_targets(
                        practitioner_id=request.practitioner_id,
                        branch_id=request.branch_id,
                        appointment_type_id=request.appointment_type_id,
                    )
                    offer = await self._require_active_offer(
                        practitioner_id=request.practitioner_id,
                        branch_id=request.branch_id,
                        appointment_type_id=request.appointment_type_id,
                        start_time=request.start_time,
                    )

                    await self._lock_practitioner(request.practitioner_id)
                    slot = await self._availability.is_slot_currently_available(
                        appointment_type_id=request.appointment_type_id,
                        practitioner_id=request.practitioner_id,
                        branch_id=request.branch_id,
                        start_time=request.start_time,
                    )
                    appointment = Appointment(
                        patient_id=patient.id,
                        practitioner_id=slot.practitioner_id,
                        branch_id=slot.branch_id,
                        appointment_type_id=slot.appointment_type_id,
                        start_time=slot.start_time,
                        end_time=slot.end_time,
                        status=AppointmentStatus.BOOKED,
                        pms_sync_status=PmsSyncStatus.PENDING,
                        created_by_call_id=created_by_call_id,
                        notes=request.notes,
                    )
                    self._appointments.add(appointment)
                    await self._session.flush()
                    self._consume_offer(offer, appointment.id)
                    appointment_type = await self._scheduling.appointment_type(
                        slot.appointment_type_id
                    )
                    assert appointment_type is not None
                    response = self._confirmation(
                        appointment,
                        patient.full_name,
                        slot.practitioner_name,
                        slot.branch_name,
                        appointment_type.name,
                    )
                    self._store_idempotency(
                        idempotency_key,
                        IdempotencyOperationType.CREATE_APPOINTMENT,
                        request_hash,
                        appointment.id,
                        response,
                    )
                    logger.info(
                        "appointment_created", appointment_id=str(appointment.id)
                    )
            await record_booking_success(replay=bool(response.idempotent_replay))
            if not response.idempotent_replay:
                try:
                    await self._pms_sync.sync_appointment(response.appointment_id)
                except Exception as exc:
                    # A committed booking must never fail because a downstream
                    # PMS worker or database is unavailable. It remains pending
                    # for reconciliation and is logged for operations.
                    logger.exception(
                        "pms_sync_post_commit_error",
                        appointment_id=str(response.appointment_id),
                        exception_type=type(exc).__name__,
                    )
            return response
        except DomainError as exc:
            await record_booking_failure(detail=exc.detail)
            raise

    async def reschedule(
        self,
        appointment_id: UUID,
        request: RescheduleAppointmentRequest,
        idempotency_key: str,
    ) -> AppointmentConfirmation:
        request_hash = self._request_hash(request)
        async with self._session.begin():
            replay = await self._idempotent_replay(
                idempotency_key,
                IdempotencyOperationType.RESCHEDULE_APPOINTMENT,
                request_hash,
            )
            if replay is not None:
                response = replay
            else:
                caller_name = require_caller_full_name(request.caller_full_name)
                appointment = await self._appointments.by_id_for_update(appointment_id)
                if appointment is None:
                    raise NotFoundError("Appointment was not found.")
                if appointment.status != AppointmentStatus.BOOKED:
                    raise ConflictError("Only a booked appointment can be rescheduled.")
                self._verify_caller_name(appointment.patient.full_name, caller_name)
                await self._assert_booking_targets(
                    practitioner_id=request.practitioner_id,
                    branch_id=request.branch_id,
                    appointment_type_id=request.appointment_type_id,
                )
                offer = await self._require_active_offer(
                    practitioner_id=request.practitioner_id,
                    branch_id=request.branch_id,
                    appointment_type_id=request.appointment_type_id,
                    start_time=request.start_time,
                )

                await self._lock_practitioner(request.practitioner_id)
                slot = await self._availability.is_slot_currently_available(
                    appointment_type_id=request.appointment_type_id,
                    practitioner_id=request.practitioner_id,
                    branch_id=request.branch_id,
                    start_time=request.start_time,
                    exclude_appointment_id=appointment.id,
                )
                fee = self._cancellation_fee(appointment)
                appointment.practitioner_id = slot.practitioner_id
                appointment.branch_id = slot.branch_id
                appointment.appointment_type_id = slot.appointment_type_id
                appointment.start_time = slot.start_time
                appointment.end_time = slot.end_time
                appointment.notes = request.notes
                # Keep the active booking in BOOKED status. `RESCHEDULED`
                # describes a historical event, not an active slot; using it
                # here would exempt the row from the DB overlap constraint.
                appointment.status = AppointmentStatus.BOOKED
                await self._session.flush()
                self._consume_offer(offer, appointment.id)
                response = self._confirmation(
                    appointment,
                    appointment.patient.full_name,
                    slot.practitioner_name,
                    slot.branch_name,
                    appointment.appointment_type.name,
                    fee,
                )
                self._store_idempotency(
                    idempotency_key,
                    IdempotencyOperationType.RESCHEDULE_APPOINTMENT,
                    request_hash,
                    appointment.id,
                    response,
                )
                logger.info(
                    "appointment_rescheduled", appointment_id=str(appointment.id)
                )
        await record_reschedule_success(replay=bool(response.idempotent_replay))
        return response

    async def cancel(
        self,
        appointment_id: UUID,
        request: CancelAppointmentRequest,
        idempotency_key: str,
    ) -> AppointmentConfirmation:
        request_hash = self._request_hash(request)
        async with self._session.begin():
            replay = await self._idempotent_replay(
                idempotency_key,
                IdempotencyOperationType.CANCEL_APPOINTMENT,
                request_hash,
            )
            if replay is not None:
                response = replay
            else:
                caller_name = require_caller_full_name(request.caller_full_name)
                appointment = await self._appointments.by_id_for_update(appointment_id)
                if appointment is None:
                    raise NotFoundError("Appointment was not found.")
                self._verify_caller_name(appointment.patient.full_name, caller_name)
                if appointment.status == AppointmentStatus.CANCELLED:
                    raise ConflictError("Appointment is already cancelled.")
                if appointment.status != AppointmentStatus.BOOKED:
                    raise ConflictError("Only a booked appointment can be cancelled.")

                fee = self._cancellation_fee(appointment)
                appointment.status = AppointmentStatus.CANCELLED
                if request.reason:
                    appointment.notes = request.reason
                await self._session.flush()
                response = self._confirmation(
                    appointment,
                    appointment.patient.full_name,
                    appointment.practitioner.display_name,
                    appointment.branch.name,
                    appointment.appointment_type.name,
                    fee,
                )
                self._store_idempotency(
                    idempotency_key,
                    IdempotencyOperationType.CANCEL_APPOINTMENT,
                    request_hash,
                    appointment.id,
                    response,
                )
                logger.info(
                    "appointment_cancelled", appointment_id=str(appointment.id)
                )
        await record_cancel_success(replay=bool(response.idempotent_replay))
        return response

    async def _assert_booking_targets(
        self,
        *,
        practitioner_id: UUID,
        branch_id: UUID,
        appointment_type_id: UUID,
    ) -> None:
        branch = await self._scheduling.branch(branch_id)
        if branch is None:
            raise NotFoundError("Branch was not found.")
        appointment_type = await self._scheduling.appointment_type(appointment_type_id)
        if appointment_type is None:
            raise NotFoundError("Appointment type was not found.")
        practitioner = await self._scheduling.practitioner(practitioner_id)
        if practitioner is None:
            raise NotFoundError("Practitioner was not found.")
        at_branch = await self._scheduling.practitioner_at_branch(
            practitioner_id, branch_id
        )
        if at_branch is None:
            raise ValidationError(
                "Practitioner does not practice at the requested branch."
            )

    async def _require_active_offer(
        self,
        *,
        practitioner_id: UUID,
        branch_id: UUID,
        appointment_type_id: UUID,
        start_time: datetime,
    ) -> AvailabilityOffer:
        if start_time.tzinfo is None:
            raise ValidationError("start_time must include a timezone offset.")
        active = await self._offers.find_active_offer(
            practitioner_id=practitioner_id,
            branch_id=branch_id,
            appointment_type_id=appointment_type_id,
            start_time=start_time,
        )
        if active is not None:
            return active

        prior = await self._offers.find_matching_offer_any_state(
            practitioner_id=practitioner_id,
            branch_id=branch_id,
            appointment_type_id=appointment_type_id,
            start_time=start_time,
        )
        if prior is None:
            raise ValidationError(
                "Booking requires a prior live availability search for this exact slot."
            )
        if prior.consumed_at is not None:
            raise ConflictError(
                "This availability offer was already confirmed; "
                "search again before booking another slot."
            )
        raise ValidationError(
            "The prior availability search has expired; search again before booking."
        )

    @staticmethod
    def _consume_offer(offer: AvailabilityOffer, appointment_id: UUID) -> None:
        offer.consumed_at = datetime.now(UTC)
        offer.consumed_by_appointment_id = appointment_id

    async def _idempotent_replay(
        self, key: str, operation: IdempotencyOperationType, request_hash: str
    ) -> AppointmentConfirmation | None:
        record = await self._appointments.idempotency_record(key, operation)
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise ConflictError(
                "Idempotency-Key was already used for a different request."
            )
        if record.response_snapshot is None:
            raise ConflictError("Idempotent operation has no stored response.")
        response = AppointmentConfirmation.model_validate(record.response_snapshot)
        return response.model_copy(update={"idempotent_replay": True})

    async def _lock_practitioner(self, practitioner_id: UUID) -> None:
        # Serializes concurrent scheduling decisions for the same
        # practitioner, including variable buffer-time checks that can't
        # be expressed in the row-level exclusion constraint alone.
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(str(practitioner_id))))
        )

    def _store_idempotency(
        self,
        key: str,
        operation: IdempotencyOperationType,
        request_hash: str,
        appointment_id: UUID,
        response: AppointmentConfirmation,
    ) -> None:
        self._appointments.add_idempotency_record(
            IdempotencyKey(
                key=key,
                operation_type=operation,
                appointment_id=appointment_id,
                request_hash=request_hash,
                response_snapshot=response.model_dump(mode="json"),
            )
        )

    @staticmethod
    def _verify_caller_name(patient_name: str, caller_name: str) -> None:
        if patient_name.casefold().strip() != caller_name.casefold().strip():
            raise ValidationError(
                "caller_full_name does not match the selected patient."
            )

    @staticmethod
    def _request_hash(request: object) -> str:
        payload = request.model_dump(mode="json")  # type: ignore[attr-defined]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _cancellation_fee(appointment: Appointment) -> FeeResult:
        appointment_type = appointment.appointment_type
        if (
            appointment_type.cancellation_fee is None
            or appointment_type.fee_window_hours is None
            or appointment.start_time - datetime.now(UTC)
            > timedelta(hours=appointment_type.fee_window_hours)
        ):
            return FeeResult(applicable=False)
        return FeeResult(
            applicable=True,
            amount=Decimal(appointment_type.cancellation_fee),
            currency=appointment_type.currency,
            fee_window_hours=appointment_type.fee_window_hours,
        )

    @staticmethod
    def _confirmation(
        appointment: Appointment,
        patient_name: str,
        practitioner_name: str,
        branch_name: str,
        appointment_type_name: str,
        fee: FeeResult | None = None,
    ) -> AppointmentConfirmation:
        return AppointmentConfirmation(
            appointment_id=appointment.id,
            patient_id=appointment.patient_id,
            practitioner_id=appointment.practitioner_id,
            practitioner_name=practitioner_name,
            branch_id=appointment.branch_id,
            branch_name=branch_name,
            appointment_type_id=appointment.appointment_type_id,
            appointment_type_name=appointment_type_name,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            status=appointment.status.value,
            cancellation_fee=fee,
        )
