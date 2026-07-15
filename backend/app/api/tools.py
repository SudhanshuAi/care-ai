"""REST tools for scheduling and escalation.

These endpoints are intentionally ordinary HTTP APIs: no Retell SDK,
WebSocket code, prompts, or voice-specific behavior belongs here. A
voice runtime can later call this surface exactly like any other client.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.followup_repository import FollowUpRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.scheduling_repository import SchedulingRepository
from app.schemas.tools import (
    AppointmentConfirmation,
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    CancelAppointmentRequest,
    CreateAppointmentRequest,
    FollowUpRequest,
    FollowUpResponse,
    PatientLookupResponse,
    RescheduleAppointmentRequest,
)
from app.services.appointment_service import AppointmentService
from app.services.availability_service import AvailabilityService
from app.services.followup_service import FollowUpService
from app.services.patient_service import PatientService
from app.deps import get_db

router = APIRouter(prefix="/tools", tags=["tools"])
DbSession = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        description="Required stable key for retries of a mutating operation.",
    ),
]


def patient_service(db: DbSession) -> PatientService:
    return PatientService(PatientRepository(db))


def availability_service(db: DbSession) -> AvailabilityService:
    return AvailabilityService(SchedulingRepository(db))


def appointment_service(db: DbSession) -> AppointmentService:
    return AppointmentService(
        db,
        AppointmentRepository(db),
        PatientRepository(db),
        SchedulingRepository(db),
    )


def followup_service(db: DbSession) -> FollowUpService:
    return FollowUpService(db, FollowUpRepository(db))


@router.get(
    "/patients/by-phone",
    response_model=PatientLookupResponse,
    summary="Find all patients mapped to a phone number",
)
async def lookup_patient_by_phone(
    phone: Annotated[str, Query(min_length=3, examples=["+91-98765-11111"])],
    service: Annotated[PatientService, Depends(patient_service)],
) -> PatientLookupResponse:
    """A shared family line produces multiple candidates and
    `requires_disambiguation: true`; this endpoint never guesses."""
    return await service.lookup_by_phone(phone)


@router.get(
    "/patients/by-name",
    response_model=PatientLookupResponse,
    summary="Find patients by a case-insensitive name fragment",
)
async def lookup_patient_by_name(
    name: Annotated[str, Query(min_length=2, examples=["Rahul Verma"])],
    service: Annotated[PatientService, Depends(patient_service)],
) -> PatientLookupResponse:
    return await service.lookup_by_name(name)


@router.post(
    "/search_availability",
    response_model=AvailabilitySearchResponse,
    summary="Read current appointment availability from the live database",
)
async def search_availability(
    request: AvailabilitySearchRequest,
    service: Annotated[AvailabilityService, Depends(availability_service)],
) -> AvailabilitySearchResponse:
    return await service.search(request)


@router.post(
    "/create_appointment",
    response_model=AppointmentConfirmation,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conflict-safe appointment",
)
async def create_appointment(
    request: CreateAppointmentRequest,
    idempotency_key: IdempotencyKey,
    service: Annotated[AppointmentService, Depends(appointment_service)],
) -> AppointmentConfirmation:
    return await service.create(request, idempotency_key)


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentConfirmation,
    summary="Atomically move an appointment after a live re-check",
)
async def reschedule_appointment(
    appointment_id: UUID,
    request: RescheduleAppointmentRequest,
    idempotency_key: IdempotencyKey,
    service: Annotated[AppointmentService, Depends(appointment_service)],
) -> AppointmentConfirmation:
    return await service.reschedule(appointment_id, request, idempotency_key)


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentConfirmation,
    summary="Cancel a booked appointment and report only applicable fees",
)
async def cancel_appointment(
    appointment_id: UUID,
    request: CancelAppointmentRequest,
    idempotency_key: IdempotencyKey,
    service: Annotated[AppointmentService, Depends(appointment_service)],
) -> AppointmentConfirmation:
    return await service.cancel(appointment_id, request, idempotency_key)


@router.post(
    "/followups",
    response_model=FollowUpResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a callback, human-request, or clinical-concern follow-up",
)
async def create_followup(
    request: FollowUpRequest,
    service: Annotated[FollowUpService, Depends(followup_service)],
) -> FollowUpResponse:
    return await service.create(request)
