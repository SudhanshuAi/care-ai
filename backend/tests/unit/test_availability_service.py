from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.schemas.tools import AvailabilitySearchRequest
from app.services.availability_service import AvailabilityService


def test_slot_granularity_rounds_up_without_losing_timezone() -> None:
    value = datetime(2026, 7, 16, 9, 2, 31, tzinfo=UTC)

    rounded = AvailabilityService._ceil_to_granularity(value)

    assert rounded == datetime(2026, 7, 16, 9, 5, tzinfo=UTC)


def test_slot_granularity_preserves_existing_five_minute_boundary() -> None:
    value = datetime(2026, 7, 16, 9, 5, tzinfo=UTC)

    assert AvailabilityService._ceil_to_granularity(value) == value


def _mock_repository(schedule: SimpleNamespace, appointment_type: SimpleNamespace, branch: SimpleNamespace) -> AsyncMock:
    repository = AsyncMock()
    repository.appointment_type.return_value = appointment_type
    repository.branch.return_value = branch
    repository.practitioner.return_value = None
    repository.eligible_schedules_in_range.return_value = [schedule]
    repository.booked_appointments_for_practitioners.return_value = []
    return repository


@pytest.mark.asyncio
async def test_search_without_date_rolls_forward_past_a_day_with_no_schedule() -> None:
    """A caller who omits appointment_date means 'starting from now', not
    'only today'. If the only matching schedule runs on a different
    weekday than today, the search must still find it instead of
    reporting zero availability."""
    appointment_type_id, branch_id, practitioner_id = uuid4(), uuid4(), uuid4()
    department_id = uuid4()

    appointment_type = SimpleNamespace(
        id=appointment_type_id,
        department_id=department_id,
        duration_minutes=20,
        buffer_minutes=0,
    )
    branch = SimpleNamespace(id=branch_id, name="Test Branch", timezone="UTC")
    practitioner = SimpleNamespace(department_id=department_id, display_name="Dr. Test")

    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)
    schedule = SimpleNamespace(
        practitioner_id=practitioner_id,
        branch_id=branch_id,
        weekday=tomorrow.strftime("%A").lower(),
        start_time=time(9, 0),
        end_time=time(17, 0),
        valid_from=None,
        valid_to=None,
        practitioner=practitioner,
        branch=branch,
    )
    repository = _mock_repository(schedule, appointment_type, branch)

    service = AvailabilityService(repository)
    response = await service.search(
        AvailabilitySearchRequest(
            appointment_type_id=appointment_type_id,
            branch_id=branch_id,
            earliest_only=True,
        ),
        record_offers=False,
    )

    assert len(response.slots) == 1
    assert response.slots[0].start_time.date() == tomorrow
    # The schedule/booking queries must run once for the whole horizon, not
    # once per candidate day, or a multi-day rollover would multiply round
    # trips to what may be a slow/remote database.
    assert repository.eligible_schedules_in_range.await_count == 1
    assert repository.booked_appointments_for_practitioners.await_count == 1


@pytest.mark.asyncio
async def test_search_rejects_explicit_past_date() -> None:
    appointment_type_id, branch_id = uuid4(), uuid4()
    department_id = uuid4()
    appointment_type = SimpleNamespace(
        id=appointment_type_id,
        department_id=department_id,
        duration_minutes=20,
        buffer_minutes=0,
    )
    branch = SimpleNamespace(id=branch_id, name="Test Branch", timezone="UTC")
    repository = AsyncMock()
    repository.appointment_type.return_value = appointment_type
    repository.branch.return_value = branch

    service = AvailabilityService(repository)
    yesterday = datetime.now(UTC).date() - timedelta(days=1)

    with pytest.raises(ValidationError, match="appointment_date is in the past"):
        await service.search(
            AvailabilitySearchRequest(
                appointment_type_id=appointment_type_id,
                branch_id=branch_id,
                appointment_date=yesterday,
            ),
            record_offers=False,
        )
