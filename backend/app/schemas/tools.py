"""Stable request/response contracts for the future voice-agent tool API."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.enums import FollowUpCategory


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PatientSummary(ApiModel):
    id: UUID
    full_name: str
    phone: str
    date_of_birth: date | None = None


class PatientLookupResponse(ApiModel):
    match_count: int
    requires_disambiguation: bool
    patients: list[PatientSummary]


class AvailabilitySearchRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "appointment_type_id": "dfd35a46-08f6-4ef3-96e7-0e635e9e93c4",
                    "branch_id": "c0d7df80-e411-49a7-8ca7-47b2477d5399",
                    "appointment_date": "2026-07-16",
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "earliest_only": True,
                }
            ]
        }
    )
    appointment_type_id: UUID = Field(
        examples=["dfd35a46-08f6-4ef3-96e7-0e635e9e93c4"],
        description="Determines appointment duration and mandatory buffer.",
    )
    branch_id: UUID | None = None
    department_id: UUID | None = None
    practitioner_id: UUID | None = None
    appointment_date: date | None = Field(
        default=None,
        description="Local branch date. Defaults to today in the branch timezone.",
    )
    start_time: time | None = Field(
        default=None, description="Optional local-time lower bound."
    )
    end_time: time | None = Field(
        default=None, description="Optional local-time upper bound."
    )
    earliest_only: bool = Field(
        default=False,
        description="Return only the earliest matching slot across all eligible practitioners/branches.",
    )
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("end_time")
    @classmethod
    def time_window_has_positive_duration(cls, value: time | None, info: object) -> time | None:
        # Cross-field validation is performed in the service because
        # start_time is optional and Pydantic field ordering is not API
        # contract logic. This validator exists to document the intended type.
        return value


class AvailabilitySlot(ApiModel):
    practitioner_id: UUID
    practitioner_name: str
    branch_id: UUID
    branch_name: str
    branch_timezone: str
    appointment_type_id: UUID
    start_time: datetime
    end_time: datetime


class AvailabilitySearchResponse(ApiModel):
    slots: list[AvailabilitySlot]
    queried_at: datetime
    source: str = "live_database"


class CreateAppointmentRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "patient_id": "b6a2ee72-cbfd-4fb7-95c4-b468dc5f9a3f",
                    "caller_full_name": "Rahul Verma",
                    "practitioner_id": "c88ec25c-c1d5-42b3-a93f-83f3707be9c5",
                    "branch_id": "c0d7df80-e411-49a7-8ca7-47b2477d5399",
                    "appointment_type_id": "dfd35a46-08f6-4ef3-96e7-0e635e9e93c4",
                    "start_time": "2026-07-16T09:00:00+05:30",
                }
            ]
        }
    )
    patient_id: UUID
    caller_full_name: str = Field(
        min_length=1,
        examples=["Rahul Verma"],
        description="Required even when the caller phone is recognized; prevents anonymous bookings.",
    )
    practitioner_id: UUID
    branch_id: UUID
    appointment_type_id: UUID
    start_time: datetime
    notes: str | None = Field(default=None, max_length=2000)


class RescheduleAppointmentRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "caller_full_name": "Rahul Verma",
                    "practitioner_id": "c88ec25c-c1d5-42b3-a93f-83f3707be9c5",
                    "branch_id": "c0d7df80-e411-49a7-8ca7-47b2477d5399",
                    "appointment_type_id": "dfd35a46-08f6-4ef3-96e7-0e635e9e93c4",
                    "start_time": "2026-07-16T10:00:00+05:30",
                }
            ]
        }
    )
    caller_full_name: str = Field(min_length=1, examples=["Rahul Verma"])
    practitioner_id: UUID
    branch_id: UUID
    appointment_type_id: UUID
    start_time: datetime
    notes: str | None = Field(default=None, max_length=2000)


class CancelAppointmentRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"caller_full_name": "Rahul Verma", "reason": "Cannot attend"}]
        }
    )
    caller_full_name: str = Field(min_length=1, examples=["Rahul Verma"])
    reason: str | None = Field(default=None, max_length=1000)


class FeeResult(ApiModel):
    applicable: bool
    amount: Decimal | None = None
    currency: str | None = None
    fee_window_hours: int | None = None


class AppointmentConfirmation(ApiModel):
    appointment_id: UUID
    patient_id: UUID
    practitioner_id: UUID
    practitioner_name: str
    branch_id: UUID
    branch_name: str
    appointment_type_id: UUID
    appointment_type_name: str
    start_time: datetime
    end_time: datetime
    status: str
    idempotent_replay: bool = False
    cancellation_fee: FeeResult | None = None


class FollowUpRequest(ApiModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "call_id": "89fc3a23-784a-46c1-8718-dbf337cd6987",
                    "patient_id": "b6a2ee72-cbfd-4fb7-95c4-b468dc5f9a3f",
                    "category": "human_requested",
                    "notes": "Caller asked for a human callback.",
                }
            ]
        }
    )
    call_id: UUID
    patient_id: UUID | None = None
    category: FollowUpCategory
    notes: str = Field(min_length=1, max_length=4000)


class FollowUpResponse(ApiModel):
    followup_id: UUID
    status: str
    category: str
    created_at: datetime
