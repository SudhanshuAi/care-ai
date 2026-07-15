"""Python enums backing every status/category column in the schema.

Each is mapped to a native PostgreSQL enum type (via `sqlalchemy.Enum`
with `native_enum=True`), so invalid values are rejected by the
database itself, not just by application code.
"""

from enum import Enum


class Weekday(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class AppointmentStatus(str, Enum):
    BOOKED = "booked"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class PmsSyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    PENDING_RETRY = "pending_retry"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISCONNECTED = "disconnected"
    RESUMED = "resumed"


class TurnRole(str, Enum):
    CALLER = "caller"
    AGENT = "agent"
    SYSTEM = "system"


class FollowUpCategory(str, Enum):
    HUMAN_REQUESTED = "human_requested"
    CLINICAL_CONCERN = "clinical_concern"
    OTHER = "other"


class FollowUpStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class IdempotencyOperationType(str, Enum):
    CREATE_APPOINTMENT = "create_appointment"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"
    PMS_WRITE_BACK = "pms_write_back"
