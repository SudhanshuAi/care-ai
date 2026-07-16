"""Live availability calculation.

There is intentionally no durable cache of "what is free right now"
beyond short-lived `AvailabilityOffer` rows. Every search loads
schedules and booked appointments from the caller's `AsyncSession`,
which is the source of truth when a caller changes their requested
time mid-conversation. Offers exist only so booking can prove a prior
live search happened and is still fresh.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions import NotFoundError, ValidationError
from app.core.guardrails import AVAILABILITY_OFFER_TTL
from app.db.models.availability_offer import AvailabilityOffer
from app.repositories.availability_offer_repository import AvailabilityOfferRepository
from app.repositories.scheduling_repository import SchedulingRepository
from app.schemas.tools import (
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    AvailabilitySlot,
)

SLOT_GRANULARITY = timedelta(minutes=5)


class AvailabilityService:
    def __init__(
        self,
        repository: SchedulingRepository,
        offers: AvailabilityOfferRepository | None = None,
    ) -> None:
        self._repository = repository
        self._offers = offers

    async def search(
        self,
        request: AvailabilitySearchRequest,
        *,
        exclude_appointment_id: UUID | None = None,
        record_offers: bool = True,
    ) -> AvailabilitySearchResponse:
        appointment_type = await self._repository.appointment_type(request.appointment_type_id)
        if appointment_type is None:
            raise NotFoundError("Appointment type was not found.")

        if request.department_id is not None and request.department_id != appointment_type.department_id:
            raise ValidationError("The appointment type does not belong to the requested department.")

        if request.branch_id is not None:
            branch = await self._repository.branch(request.branch_id)
            if branch is None:
                raise NotFoundError("Branch was not found.")

        if request.practitioner_id is not None:
            practitioner = await self._repository.practitioner(request.practitioner_id)
            if practitioner is None:
                raise NotFoundError("Practitioner was not found.")

        if request.start_time and request.end_time and request.start_time >= request.end_time:
            raise ValidationError("start_time must be before end_time.")

        local_date = request.appointment_date or await self._today_for_request(request)
        schedules = await self._repository.eligible_schedules(
            department_id=request.department_id or appointment_type.department_id,
            practitioner_id=request.practitioner_id,
            branch_id=request.branch_id,
            local_date=local_date,
        )

        slots: list[AvailabilitySlot] = []
        duration = timedelta(minutes=appointment_type.duration_minutes)
        buffer = timedelta(minutes=appointment_type.buffer_minutes)

        for schedule in schedules:
            if schedule.practitioner.department_id != appointment_type.department_id:
                continue

            zone = ZoneInfo(schedule.branch.timezone)
            schedule_start = datetime.combine(local_date, schedule.start_time, tzinfo=zone)
            schedule_end = datetime.combine(local_date, schedule.end_time, tzinfo=zone)
            lower_bound = (
                datetime.combine(local_date, request.start_time, tzinfo=zone)
                if request.start_time
                else schedule_start
            )
            upper_bound = (
                datetime.combine(local_date, request.end_time, tzinfo=zone)
                if request.end_time
                else schedule_end
            )
            candidate = self._ceil_to_granularity(max(schedule_start, lower_bound))
            latest_start = min(schedule_end, upper_bound) - duration - buffer

            # Query once per live schedule window. The extra buffer on
            # both ends ensures a candidate cannot sit immediately next
            # to an existing appointment when the appointment type
            # requires a gap.
            booked = await self._repository.booked_appointments(
                practitioner_id=schedule.practitioner_id,
                period_start=(schedule_start - buffer).astimezone(UTC),
                period_end=(schedule_end + buffer).astimezone(UTC),
                exclude_appointment_id=exclude_appointment_id,
            )

            while candidate <= latest_start:
                candidate_end = candidate + duration
                candidate_block_start = candidate - buffer
                candidate_block_end = candidate_end + buffer
                if not any(
                    appointment.start_time < candidate_block_end.astimezone(UTC)
                    and appointment.end_time > candidate_block_start.astimezone(UTC)
                    for appointment in booked
                ):
                    slots.append(
                        AvailabilitySlot(
                            practitioner_id=schedule.practitioner_id,
                            practitioner_name=schedule.practitioner.display_name,
                            branch_id=schedule.branch_id,
                            branch_name=schedule.branch.name,
                            branch_timezone=schedule.branch.timezone,
                            appointment_type_id=appointment_type.id,
                            start_time=candidate.astimezone(UTC),
                            end_time=candidate_end.astimezone(UTC),
                        )
                    )
                candidate += SLOT_GRANULARITY

        slots.sort(key=lambda slot: (slot.start_time, slot.branch_name, slot.practitioner_name))
        result = slots[:1] if request.earliest_only else slots[: request.limit]
        queried_at = datetime.now(UTC)
        if record_offers and self._offers is not None:
            await self._persist_offers(result, queried_at)
        return AvailabilitySearchResponse(slots=result, queried_at=queried_at)

    async def is_slot_currently_available(
        self,
        *,
        appointment_type_id: UUID,
        practitioner_id: UUID,
        branch_id: UUID,
        start_time: datetime,
        exclude_appointment_id: UUID | None = None,
    ) -> AvailabilitySlot:
        """Re-run a live availability query for an exact requested slot."""

        if start_time.tzinfo is None:
            raise ValidationError("start_time must include a timezone offset.")
        branch = await self._repository.branch(branch_id)
        if branch is None:
            raise NotFoundError("Branch was not found.")
        appointment_type = await self._repository.appointment_type(appointment_type_id)
        if appointment_type is None:
            raise NotFoundError("Appointment type was not found.")
        practitioner = await self._repository.practitioner(practitioner_id)
        if practitioner is None:
            raise NotFoundError("Practitioner was not found.")
        local_start = start_time.astimezone(ZoneInfo(branch.timezone))
        response = await self.search(
            AvailabilitySearchRequest(
                appointment_type_id=appointment_type_id,
                practitioner_id=practitioner_id,
                branch_id=branch_id,
                appointment_date=local_start.date(),
                start_time=local_start.time().replace(tzinfo=None),
                end_time=(
                    local_start
                    + timedelta(
                        minutes=appointment_type.duration_minutes
                        + appointment_type.buffer_minutes
                    )
                ).time().replace(tzinfo=None),
                limit=1,
            ),
            exclude_appointment_id=exclude_appointment_id,
            record_offers=False,
        )
        for slot in response.slots:
            if slot.start_time == start_time.astimezone(UTC):
                return slot
        raise ValidationError("The requested slot is no longer available.")

    async def _persist_offers(
        self, slots: list[AvailabilitySlot], searched_at: datetime
    ) -> None:
        assert self._offers is not None
        expires_at = searched_at + AVAILABILITY_OFFER_TTL
        offers = [
            AvailabilityOffer(
                practitioner_id=slot.practitioner_id,
                branch_id=slot.branch_id,
                appointment_type_id=slot.appointment_type_id,
                start_time=slot.start_time,
                end_time=slot.end_time,
                searched_at=searched_at,
                expires_at=expires_at,
            )
            for slot in slots
        ]
        await self._offers.persist_new(offers)

    async def _today_for_request(self, request: AvailabilitySearchRequest) -> date:
        if request.branch_id is None:
            # The seed data's clinic timezone is Asia/Kolkata. A
            # cross-branch unqualified request needs a defined locale;
            # production call context will provide one. UTC is safe and
            # deterministic until then.
            return datetime.now(UTC).date()
        branch = await self._repository.branch(request.branch_id)
        if branch is None:
            raise NotFoundError("Branch was not found.")
        return datetime.now(ZoneInfo(branch.timezone)).date()

    @staticmethod
    def _ceil_to_granularity(value: datetime) -> datetime:
        remainder = value.minute % 5
        if remainder or value.second or value.microsecond:
            value += timedelta(minutes=(5 - remainder) % 5)
        return value.replace(second=0, microsecond=0)
