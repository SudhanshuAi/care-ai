"""Live availability calculation.

There is intentionally no durable cache of "what is free right now"
beyond short-lived `AvailabilityOffer` rows. Every search loads
schedules and booked appointments from the caller's `AsyncSession`,
which is the source of truth when a caller changes their requested
time mid-conversation. Offers exist only so booking can prove a prior
live search happened and is still fresh.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions import NotFoundError, ValidationError
from app.core.guardrails import AVAILABILITY_OFFER_TTL
from app.db.models.appointment import Appointment
from app.db.models.appointment_type import AppointmentType
from app.db.models.availability_offer import AvailabilityOffer
from app.db.models.practitioner_schedule import PractitionerSchedule
from app.repositories.availability_offer_repository import AvailabilityOfferRepository
from app.repositories.scheduling_repository import SchedulingRepository
from app.schemas.tools import (
    AvailabilitySearchRequest,
    AvailabilitySearchResponse,
    AvailabilitySlot,
)

SLOT_GRANULARITY = timedelta(minutes=5)

# How far ahead to look when the caller didn't name a specific date (e.g.
# "book the earliest slot"). Without this, a search made in the evening --
# after a branch's only block for that appointment type has passed for the
# day -- would report zero slots even though tomorrow (or later this week)
# is wide open.
SEARCH_HORIZON_DAYS = 30


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

        reference_today = await self._today_for_request(request)
        if request.appointment_date is not None:
            if request.appointment_date < reference_today:
                # LLM callers sometimes miscompute "today"/"earliest" and
                # pass an explicit past date. Reject deterministically
                # instead of silently offering stale slots on a date that
                # has already passed -- the caller-facing fix is to omit
                # appointment_date for same-day/earliest requests and let
                # this default to today.
                raise ValidationError(
                    "appointment_date is in the past. Omit appointment_date "
                    "for 'today'/'earliest available' requests, or use "
                    "today's date or later."
                )
            candidate_dates = [request.appointment_date]
        else:
            # No date named: search forward from today instead of only
            # checking today, so a quiet evening or a fully-booked today
            # doesn't get reported as "no availability" when tomorrow (or
            # later this month) is open.
            candidate_dates = [
                reference_today + timedelta(days=offset)
                for offset in range(SEARCH_HORIZON_DAYS)
            ]

        # Fetch schedules and booked appointments once for the whole
        # candidate window (not once per day) so a multi-day "earliest
        # available" rollover doesn't multiply round trips to what may be
        # a slow/remote database -- it stays O(1) queries regardless of
        # how many days it takes to find an open slot.
        schedules = await self._repository.eligible_schedules_in_range(
            department_id=request.department_id or appointment_type.department_id,
            practitioner_id=request.practitioner_id,
            branch_id=request.branch_id,
            start_date=candidate_dates[0],
            end_date=candidate_dates[-1],
        )
        schedules = [
            schedule
            for schedule in schedules
            if schedule.practitioner.department_id == appointment_type.department_id
        ]
        booked_by_practitioner = await self._booked_by_practitioner(
            schedules, candidate_dates[0], candidate_dates[-1], exclude_appointment_id
        )

        slots: list[AvailabilitySlot] = []
        queried_at = datetime.now(UTC)
        for local_date in candidate_dates:
            slots = self._slots_for_day(
                request, appointment_type, local_date, schedules, booked_by_practitioner
            )
            if slots:
                break

        result = slots[:1] if request.earliest_only else slots[: request.limit]
        if record_offers and self._offers is not None:
            await self._persist_offers(result, queried_at)
        return AvailabilitySearchResponse(slots=result, queried_at=queried_at)

    async def _booked_by_practitioner(
        self,
        schedules: list[PractitionerSchedule],
        start_date: date,
        end_date: date,
        exclude_appointment_id: UUID | None,
    ) -> dict[UUID, list[Appointment]]:
        practitioner_ids = {schedule.practitioner_id for schedule in schedules}
        if not practitioner_ids:
            return {}
        # Pad a day on each side so a branch's local-timezone day doesn't
        # spill past this UTC window and miss an adjacent booking.
        period_start = datetime.combine(start_date, time.min, tzinfo=UTC) - timedelta(days=1)
        period_end = datetime.combine(end_date, time.max, tzinfo=UTC) + timedelta(days=1)
        booked = await self._repository.booked_appointments_for_practitioners(
            practitioner_ids=practitioner_ids,
            period_start=period_start,
            period_end=period_end,
            exclude_appointment_id=exclude_appointment_id,
        )
        by_practitioner: dict[UUID, list[Appointment]] = defaultdict(list)
        for appointment in booked:
            by_practitioner[appointment.practitioner_id].append(appointment)
        return by_practitioner

    def _slots_for_day(
        self,
        request: AvailabilitySearchRequest,
        appointment_type: AppointmentType,
        local_date: date,
        schedules: list[PractitionerSchedule],
        booked_by_practitioner: dict[UUID, list[Appointment]],
    ) -> list[AvailabilitySlot]:
        weekday = local_date.strftime("%A").lower()
        slots: list[AvailabilitySlot] = []
        duration = timedelta(minutes=appointment_type.duration_minutes)
        buffer = timedelta(minutes=appointment_type.buffer_minutes)

        for schedule in schedules:
            if schedule.weekday != weekday:
                continue
            if schedule.valid_from is not None and schedule.valid_from > local_date:
                continue
            if schedule.valid_to is not None and schedule.valid_to < local_date:
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
            # For a same-day search, never offer a slot that has already
            # passed. For a future date this `now` is naturally earlier
            # than schedule_start and has no effect.
            now_in_zone = datetime.now(UTC).astimezone(zone)
            candidate = self._ceil_to_granularity(
                max(schedule_start, lower_bound, now_in_zone)
            )
            latest_start = min(schedule_end, upper_bound) - duration - buffer
            booked = booked_by_practitioner.get(schedule.practitioner_id, [])

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
                            # Computed in the branch-local zone (`candidate`,
                            # pre-UTC-conversion) so the agent never has to do
                            # its own UTC-to-local/AM-PM math, which it gets
                            # wrong on Z-suffixed timestamps.
                            start_time_display=self._format_local(candidate),
                        )
                    )
                candidate += SLOT_GRANULARITY

        slots.sort(key=lambda slot: (slot.start_time, slot.branch_name, slot.practitioner_name))
        return slots

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
    def _format_local(value: datetime) -> str:
        # e.g. "Sat, 18 Jul, 9:00 AM" -- strip a leading zero from the
        # hour ("09:00 AM" -> "9:00 AM") since %-I is not portable.
        formatted = value.strftime("%a, %d %b, %I:%M %p")
        hour, _, rest = formatted.partition(":")
        *prefix, hour_value = hour.rsplit(" ", 1)
        if hour_value.startswith("0"):
            hour_value = hour_value[1:]
        return " ".join([*prefix, hour_value]) + ":" + rest

    @staticmethod
    def _ceil_to_granularity(value: datetime) -> datetime:
        remainder = value.minute % 5
        if remainder or value.second or value.microsecond:
            value += timedelta(minutes=(5 - remainder) % 5)
        return value.replace(second=0, microsecond=0)
