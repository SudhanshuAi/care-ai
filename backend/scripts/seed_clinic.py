"""Populate the database with a starter clinic dataset: one clinic,
two branches, several departments/doctors with branch assignments and
weekly schedules, appointment types, and a handful of sample patients.

NOTE ON DATA PROVENANCE: the clinic/branch/doctor details below are
placeholder-realistic data for exercising the schema end to end during
scaffolding. The assignment requires the final dataset to be a real
clinic "sourced not invented" (e.g. via a Cliniko trial export). Replace
this data before treating it as the submission's dataset.

Safe to re-run: it does not duplicate the clinic data. It also ensures
the future, marked live-demo appointment fixtures are present.

Usage (from the `backend/` directory, or via `docker compose exec
backend ...`):

    python -m scripts.seed_clinic
"""

import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.models import (
    Appointment,
    AppointmentType,
    Branch,
    Clinic,
    Department,
    Patient,
    Practitioner,
    PractitionerBranch,
    PractitionerSchedule,
)
from app.db.models.enums import AppointmentStatus, PmsSyncStatus, Weekday
from app.db.session import session_scope

logger = get_logger(__name__)

CLINIC_NAME = "Sunrise Multispecialty Clinic"

WEEKDAYS_MON_SAT = [
    Weekday.MONDAY,
    Weekday.TUESDAY,
    Weekday.WEDNESDAY,
    Weekday.THURSDAY,
    Weekday.FRIDAY,
    Weekday.SATURDAY,
]

MORNING_BLOCK = (dt.time(9, 0), dt.time(13, 0))
AFTERNOON_BLOCK = (dt.time(14, 0), dt.time(18, 0))
CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")

# These notes identify rows created exclusively for live-demo testing.
TEST_APPOINTMENT_MARKER = "[live-demo-fixture]"


async def seed() -> None:
    async with session_scope() as db:
        existing = await db.scalar(select(Clinic).where(Clinic.name == CLINIC_NAME))
        if existing is not None:
            await _seed_test_appointments(db)
            logger.info("seed_skipped_already_present", clinic_id=str(existing.id))
            return

        clinic = Clinic(
            name=CLINIC_NAME,
            default_timezone="Asia/Kolkata",
            default_currency="INR",
        )
        db.add(clinic)
        await db.flush()

        koramangala = Branch(
            clinic_id=clinic.id,
            name="Koramangala Branch",
            address="80 Feet Road, Koramangala 4th Block, Bengaluru, Karnataka 560034",
            timezone="Asia/Kolkata",
            phone="+91-80-4111-2222",
        )
        indiranagar = Branch(
            clinic_id=clinic.id,
            name="Indiranagar Branch",
            address="100 Feet Road, Indiranagar, Bengaluru, Karnataka 560038",
            timezone="Asia/Kolkata",
            phone="+91-80-4111-3333",
        )
        db.add_all([koramangala, indiranagar])
        await db.flush()

        dentistry = Department(clinic_id=clinic.id, name="General Dentistry")
        physio = Department(clinic_id=clinic.id, name="Physiotherapy")
        dermatology = Department(clinic_id=clinic.id, name="Dermatology")
        pediatrics = Department(clinic_id=clinic.id, name="Pediatrics")
        db.add_all([dentistry, physio, dermatology, pediatrics])
        await db.flush()

        db.add_all(
            [
                AppointmentType(
                    department_id=dentistry.id,
                    name="Dental Checkup",
                    duration_minutes=30,
                    buffer_minutes=10,
                    price=800,
                    currency="INR",
                    cancellation_fee=200,
                    fee_window_hours=24,
                ),
                AppointmentType(
                    department_id=physio.id,
                    name="Physiotherapy Session",
                    duration_minutes=45,
                    buffer_minutes=15,
                    price=1200,
                    currency="INR",
                    cancellation_fee=300,
                    fee_window_hours=24,
                ),
                AppointmentType(
                    department_id=dermatology.id,
                    name="Dermatology Consultation",
                    duration_minutes=20,
                    buffer_minutes=5,
                    price=900,
                    currency="INR",
                    cancellation_fee=None,
                    fee_window_hours=None,
                ),
                AppointmentType(
                    department_id=pediatrics.id,
                    name="Pediatric Consultation",
                    duration_minutes=20,
                    buffer_minutes=5,
                    price=700,
                    currency="INR",
                    cancellation_fee=None,
                    fee_window_hours=None,
                ),
            ]
        )

        # (display_name, title, department, branches, hour_blocks)
        # Deliberately varied hours per doctor/branch so availability
        # search has something non-trivial to chew on later: some
        # doctors are full-day at one branch, morning-only at another.
        practitioners_spec = [
            (
                "Dr. Ananya Rao",
                "BDS, MDS",
                dentistry,
                [
                    (koramangala, [MORNING_BLOCK, AFTERNOON_BLOCK]),
                    (indiranagar, [MORNING_BLOCK]),
                ],
            ),
            (
                "Dr. Karthik Iyer",
                "BDS",
                dentistry,
                [(koramangala, [MORNING_BLOCK, AFTERNOON_BLOCK])],
            ),
            (
                "Dr. Meera Nair",
                "BPT, MPT",
                physio,
                [(indiranagar, [MORNING_BLOCK, AFTERNOON_BLOCK])],
            ),
            (
                "Dr. Sanjay Gupta",
                "MBBS, MD (Dermatology)",
                dermatology,
                [
                    (koramangala, [AFTERNOON_BLOCK]),
                    (indiranagar, [MORNING_BLOCK, AFTERNOON_BLOCK]),
                ],
            ),
            (
                "Dr. Priya Sharma",
                "MBBS, DCH",
                pediatrics,
                [(indiranagar, [MORNING_BLOCK])],
            ),
        ]

        for display_name, title, department, branch_specs in practitioners_spec:
            practitioner = Practitioner(
                clinic_id=clinic.id,
                department_id=department.id,
                display_name=display_name,
                title=title,
            )
            db.add(practitioner)
            await db.flush()

            for index, (branch, hour_blocks) in enumerate(branch_specs):
                db.add(
                    PractitionerBranch(
                        practitioner_id=practitioner.id,
                        branch_id=branch.id,
                        is_primary=(index == 0),
                    )
                )
                for weekday in WEEKDAYS_MON_SAT:
                    for start_time, end_time in hour_blocks:
                        db.add(
                            PractitionerSchedule(
                                practitioner_id=practitioner.id,
                                branch_id=branch.id,
                                weekday=weekday,
                                start_time=start_time,
                                end_time=end_time,
                            )
                        )

        patients = [
            Patient(
                full_name="Rahul Verma",
                phone="+91-98765-10001",
                date_of_birth=dt.date(1990, 4, 12),
            ),
            Patient(
                full_name="Sneha Kulkarni",
                phone="+91-98765-10002",
                date_of_birth=dt.date(1985, 11, 2),
            ),
            # Shared phone line -- exercises the "two patients, one
            # phone number" disambiguation scenario from the assignment.
            Patient(
                full_name="Arjun Mehta",
                phone="+91-98765-11111",
                date_of_birth=dt.date(1978, 6, 23),
            ),
            Patient(
                full_name="Kavya Mehta",
                phone="+91-98765-11111",
                date_of_birth=dt.date(1980, 9, 15),
            ),
            Patient(
                full_name="Fatima Sheikh",
                phone="+91-98765-10004",
                date_of_birth=dt.date(1995, 1, 30),
            ),
        ]
        db.add_all(patients)
        await db.flush()
        await _seed_test_appointments(db)

        logger.info(
            "seed_completed",
            clinic=CLINIC_NAME,
            branches=2,
            departments=4,
            practitioners=len(practitioners_spec),
            patients=len(patients),
        )


async def _seed_test_appointments(db: AsyncSession) -> None:
    """Create future appointments for live cancellation and reschedule tests."""

    next_clinic_day = _next_clinic_day()
    now = dt.datetime.now(dt.UTC)
    fixture_specs = [
        (
            "Rahul Verma",
            "Dr. Ananya Rao",
            "Koramangala Branch",
            "Dental Checkup",
            dt.time(11, 0),
            "rahul-cancel",
        ),
        (
            "Sneha Kulkarni",
            "Dr. Sanjay Gupta",
            "Indiranagar Branch",
            "Dermatology Consultation",
            dt.time(15, 0),
            "sneha-reschedule",
        ),
        (
            "Fatima Sheikh",
            "Dr. Meera Nair",
            "Indiranagar Branch",
            "Physiotherapy Session",
            dt.time(16, 0),
            "fatima-list",
        ),
    ]

    for (
        patient_name,
        practitioner_name,
        branch_name,
        appointment_type_name,
        local_start_time,
        fixture_name,
    ) in fixture_specs:
        marker = f"{TEST_APPOINTMENT_MARKER} {fixture_name}"
        existing = await db.scalar(
            select(Appointment).where(
                Appointment.notes == marker,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.start_time > now,
            )
        )
        if existing is not None:
            continue

        patient = await db.scalar(select(Patient).where(Patient.full_name == patient_name))
        practitioner = await db.scalar(
            select(Practitioner).where(Practitioner.display_name == practitioner_name)
        )
        branch = await db.scalar(select(Branch).where(Branch.name == branch_name))
        appointment_type = await db.scalar(
            select(AppointmentType).where(AppointmentType.name == appointment_type_name)
        )
        if not all((patient, practitioner, branch, appointment_type)):
            raise RuntimeError(f"Unable to create test fixture {fixture_name}: seed data is incomplete.")

        local_start = dt.datetime.combine(
            next_clinic_day, local_start_time, tzinfo=CLINIC_TIMEZONE
        )
        db.add(
            Appointment(
                patient_id=patient.id,
                practitioner_id=practitioner.id,
                branch_id=branch.id,
                appointment_type_id=appointment_type.id,
                start_time=local_start.astimezone(dt.UTC),
                end_time=(
                    local_start
                    + dt.timedelta(minutes=appointment_type.duration_minutes)
                ).astimezone(dt.UTC),
                status=AppointmentStatus.BOOKED,
                pms_sync_status=PmsSyncStatus.SYNCED,
                notes=marker,
            )
        )

    await db.flush()
    logger.info("test_appointments_seeded", appointment_date=next_clinic_day.isoformat())


def _next_clinic_day() -> dt.date:
    """Return the next Monday-Saturday date in the clinic's local timezone."""

    candidate = dt.datetime.now(CLINIC_TIMEZONE).date() + dt.timedelta(days=1)
    while candidate.weekday() == 6:  # Sunday
        candidate += dt.timedelta(days=1)
    return candidate


async def main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
