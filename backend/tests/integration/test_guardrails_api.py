"""Integration coverage for backend-authoritative booking guardrails."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, update

from app.db.models import AppointmentType, Branch, Call, Patient
from app.db.models.availability_offer import AvailabilityOffer
from app.db.models.enums import CallDirection, FollowUpCategory
from app.db.session import session_scope
from app.main import app
from scripts.seed_clinic import seed


async def _seed_ids() -> tuple[str, str, str]:
    await seed()
    async with session_scope() as session:
        appointment_type = await session.scalar(select(AppointmentType).limit(1))
        branch = await session.scalar(select(Branch).order_by(Branch.name).limit(1))
        patient = await session.scalar(
            select(Patient).where(Patient.full_name == "Rahul Verma")
        )
        assert appointment_type and branch and patient
        return str(appointment_type.id), str(branch.id), str(patient.id)


async def _first_slot(
    client: httpx.AsyncClient, appointment_type_id: str, branch_id: str
) -> dict:
    target_date = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
    availability = await client.post(
        "/tools/search_availability",
        json={
            "appointment_type_id": appointment_type_id,
            "branch_id": branch_id,
            "appointment_date": target_date,
            "limit": 1,
        },
    )
    assert availability.status_code == 200
    slots = availability.json()["slots"]
    if not slots:
        pytest.skip("Seeded branch has no schedule on the generated date.")
    return slots[0]


@pytest.mark.asyncio
async def test_booking_without_prior_search_is_rejected() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Search once to learn a real slot shape, then book a different start
        # time that was never offered.
        slot = await _first_slot(client, appointment_type_id, branch_id)
        forged_start = (
            datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
            + timedelta(minutes=35)
        ).isoformat()
        response = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": slot["practitioner_id"],
                "branch_id": slot["branch_id"],
                "appointment_type_id": appointment_type_id,
                "start_time": forged_start,
            },
            headers={"Idempotency-Key": f"guard-no-search-{uuid4()}"},
        )

    assert response.status_code == 422
    assert "prior live availability search" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_booking_rejects_stale_availability_offer() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        slot = await _first_slot(client, appointment_type_id, branch_id)

    async with session_scope() as session:
        await session.execute(
            update(AvailabilityOffer).values(
                expires_at=datetime.now(UTC) - timedelta(minutes=1)
            )
        )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": slot["practitioner_id"],
                "branch_id": slot["branch_id"],
                "appointment_type_id": appointment_type_id,
                "start_time": slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-stale-{uuid4()}"},
        )

    assert response.status_code == 422
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_double_confirmation_is_rejected() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        slot = await _first_slot(client, appointment_type_id, branch_id)
        payload = {
            "patient_id": patient_id,
            "caller_full_name": "Rahul Verma",
            "practitioner_id": slot["practitioner_id"],
            "branch_id": slot["branch_id"],
            "appointment_type_id": appointment_type_id,
            "start_time": slot["start_time"],
        }
        first = await client.post(
            "/tools/create_appointment",
            json=payload,
            headers={"Idempotency-Key": f"guard-confirm-1-{uuid4()}"},
        )
        second = await client.post(
            "/tools/create_appointment",
            json=payload,
            headers={"Idempotency-Key": f"guard-confirm-2-{uuid4()}"},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "already confirmed" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_hallucinated_practitioner_is_not_found() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        slot = await _first_slot(client, appointment_type_id, branch_id)
        response = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": str(uuid4()),
                "branch_id": slot["branch_id"],
                "appointment_type_id": appointment_type_id,
                "start_time": slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-prac-{uuid4()}"},
        )

    assert response.status_code == 404
    assert "practitioner" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_branch_and_appointment_type_are_not_found() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        slot = await _first_slot(client, appointment_type_id, branch_id)
        bad_branch = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": slot["practitioner_id"],
                "branch_id": str(uuid4()),
                "appointment_type_id": appointment_type_id,
                "start_time": slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-branch-{uuid4()}"},
        )
        bad_type = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": slot["practitioner_id"],
                "branch_id": slot["branch_id"],
                "appointment_type_id": str(uuid4()),
                "start_time": slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-type-{uuid4()}"},
        )

    assert bad_branch.status_code == 404
    assert "branch" in bad_branch.json()["detail"].lower()
    assert bad_type.status_code == 404
    assert "appointment type" in bad_type.json()["detail"].lower()


@pytest.mark.asyncio
async def test_booking_without_caller_name_is_rejected() -> None:
    appointment_type_id, branch_id, patient_id = await _seed_ids()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        slot = await _first_slot(client, appointment_type_id, branch_id)
        response = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "   ",
                "practitioner_id": slot["practitioner_id"],
                "branch_id": slot["branch_id"],
                "appointment_type_id": appointment_type_id,
                "start_time": slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-name-{uuid4()}"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_same_patient_cannot_double_book_overlapping_time() -> None:
    """Two different practitioners, same patient, overlapping time -> 409.

    The practitioner-scoped `uq_appointment_no_overlap` constraint alone
    would allow this (different practitioners don't collide), which is
    exactly the "duplicate appointment" gap this guardrail closes.
    """

    await seed()
    async with session_scope() as session:
        dental_type = await session.scalar(
            select(AppointmentType).where(AppointmentType.name == "Dental Checkup")
        )
        koramangala = await session.scalar(
            select(Branch).where(Branch.name.ilike("%koramangala%"))
        )
        patient = await session.scalar(
            select(Patient).where(Patient.full_name == "Rahul Verma")
        )
        assert dental_type and koramangala and patient
        appointment_type_id = str(dental_type.id)
        branch_id = str(koramangala.id)
        patient_id = str(patient.id)

    transport = httpx.ASGITransport(app=app)
    target_date = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        availability = await client.post(
            "/tools/search_availability",
            json={
                "appointment_type_id": appointment_type_id,
                "branch_id": branch_id,
                "appointment_date": target_date,
                "limit": 10,
            },
        )
        assert availability.status_code == 200
        slots = availability.json()["slots"]
        by_start: dict[str, list[dict]] = {}
        for slot in slots:
            by_start.setdefault(slot["start_time"], []).append(slot)
        overlapping_pair = next(
            (
                group
                for group in by_start.values()
                if len({slot["practitioner_id"] for slot in group}) > 1
            ),
            None,
        )
        if overlapping_pair is None:
            pytest.skip(
                "Seeded branch has no two practitioners free at the same slot."
            )
        first_slot, second_slot = overlapping_pair[0], overlapping_pair[1]

        first = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": first_slot["practitioner_id"],
                "branch_id": first_slot["branch_id"],
                "appointment_type_id": appointment_type_id,
                "start_time": first_slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-dupe-1-{uuid4()}"},
        )
        second = await client.post(
            "/tools/create_appointment",
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": second_slot["practitioner_id"],
                "branch_id": second_slot["branch_id"],
                "appointment_type_id": appointment_type_id,
                "start_time": second_slot["start_time"],
            },
            headers={"Idempotency-Key": f"guard-dupe-2-{uuid4()}"},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "already has a booked appointment" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_followup_rejects_immediate_transfer_and_duplicates() -> None:
    await seed()
    async with session_scope() as session:
        call = Call(
            retell_call_id=f"followup-guard-{uuid4()}",
            phone="+91-98765-10001",
            direction=CallDirection.INBOUND,
        )
        session.add(call)
        await session.flush()
        call_id = str(call.id)

    transport = httpx.ASGITransport(app=app)
    payload = {
        "call_id": call_id,
        "category": FollowUpCategory.HUMAN_REQUESTED.value,
        "notes": "Caller asked for a human callback about prescriptions.",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        transfer = await client.post(
            "/tools/followups",
            json={
                **payload,
                "notes": "I will transfer you now to a receptionist.",
            },
        )
        first = await client.post("/tools/followups", json=payload)
        duplicate = await client.post("/tools/followups", json=payload)

    assert transfer.status_code == 422
    assert "immediate" in transfer.json()["detail"].lower()
    assert first.status_code == 201
    assert "call the patient back" in first.json()["callback_expectation"].lower()
    assert "immediate live transfer" in first.json()["callback_expectation"].lower()
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"].lower()
