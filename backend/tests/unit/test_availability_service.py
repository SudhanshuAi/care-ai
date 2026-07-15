from datetime import UTC, datetime

from app.services.availability_service import AvailabilityService


def test_slot_granularity_rounds_up_without_losing_timezone() -> None:
    value = datetime(2026, 7, 16, 9, 2, 31, tzinfo=UTC)

    rounded = AvailabilityService._ceil_to_granularity(value)

    assert rounded == datetime(2026, 7, 16, 9, 5, tzinfo=UTC)


def test_slot_granularity_preserves_existing_five_minute_boundary() -> None:
    value = datetime(2026, 7, 16, 9, 5, tzinfo=UTC)

    assert AvailabilityService._ceil_to_granularity(value) == value
