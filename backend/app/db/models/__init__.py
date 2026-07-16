"""Import every model module so its class is registered on `Base.metadata`.

Anything that needs the full metadata populated -- Alembic's `env.py`
(for autogenerate) and the seed script -- imports this package (or the
names re-exported below) rather than individual model modules, so
there is exactly one place that has to remember "import every model".
"""

from app.db.models.appointment import Appointment
from app.db.models.appointment_type import AppointmentType
from app.db.models.availability_offer import AvailabilityOffer
from app.db.models.branch import Branch
from app.db.models.call import Call
from app.db.models.call_turn import CallTurn
from app.db.models.clinic import Clinic
from app.db.models.department import Department
from app.db.models.followup import FollowUp
from app.db.models.idempotency_key import IdempotencyKey
from app.db.models.metric_event import MetricEvent
from app.db.models.patient import Patient
from app.db.models.practitioner import Practitioner
from app.db.models.practitioner_branch import PractitionerBranch
from app.db.models.practitioner_schedule import PractitionerSchedule

__all__ = [
    "Appointment",
    "AppointmentType",
    "AvailabilityOffer",
    "Branch",
    "Call",
    "CallTurn",
    "Clinic",
    "Department",
    "FollowUp",
    "IdempotencyKey",
    "MetricEvent",
    "Patient",
    "Practitioner",
    "PractitionerBranch",
    "PractitionerSchedule",
]
