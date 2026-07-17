"""Run repeatable end-to-end backend evaluations against a dedicated database.

Run from ``backend/`` with ``EVALUATION_DATABASE_URL`` set.  The runner uses
the real ASGI app, HTTP routes, services, and PostgreSQL transactions; it never
uses a provider account or mocks scheduling business rules.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4


def _configure_evaluation_database() -> None:
    evaluation_url = os.environ.get("EVALUATION_DATABASE_URL", "").strip()
    configured_url = os.environ.get("DATABASE_URL", "").strip()
    if not evaluation_url:
        raise RuntimeError("EVALUATION_DATABASE_URL is required; refusing to use DATABASE_URL.")
    if evaluation_url == configured_url:
        raise RuntimeError(
            "EVALUATION_DATABASE_URL must be a dedicated database, not DATABASE_URL."
        )
    os.environ["DATABASE_URL"] = evaluation_url


_configure_evaluation_database()

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db.models import Appointment, Call, IdempotencyKey  # noqa: E402
from app.db.session import dispose_engine, session_scope  # noqa: E402
from app.main import app  # noqa: E402
from evaluation.metrics import CaseResult, StepResult, build_report  # noqa: E402
from evaluation.report import write_reports  # noqa: E402
from scripts.seed_clinic import seed  # noqa: E402

CASES_PATH = Path(__file__).with_name("cases.json")


class Harness:
    def __init__(self, client: httpx.AsyncClient, run_id: str) -> None:
        self.client = client
        self.run_id = run_id

    def call_id(self, case_id: str) -> str:
        return f"eval:{self.run_id}:{case_id}:{uuid4()}"

    async def request(
        self,
        result: CaseResult,
        name: str,
        method: str,
        url: str,
        *,
        expected: set[int],
        tool: str | None = None,
        booking: bool = False,
        retry: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        response = await self.client.request(method, url, **kwargs)
        latency_ms = (time.perf_counter() - started) * 1000
        ok = response.status_code in expected
        payload: dict[str, Any]
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {"raw": response.text}
        result.steps.append(
            StepResult(
                name=name,
                success=ok,
                latency_ms=round(latency_ms, 2),
                status_code=response.status_code,
                tool=tool,
                booking_operation=booking,
                retry=retry,
                detail=None if ok else str(payload),
            )
        )
        if not ok:
            raise AssertionError(f"{name}: expected {expected}, got {response.status_code}: {payload}")
        return payload

    async def catalog(self, result: CaseResult, case_id: str) -> dict[str, Any]:
        body = await self.request(
            result,
            "get_clinic_catalog",
            "POST",
            "/webhooks/retell/tools",
            expected={200},
            tool="get_clinic_catalog",
            json={
                "name": "get_clinic_catalog",
                "args": {},
                "call": {"call_id": self.call_id(case_id), "from_number": "+910000000000"},
            },
        )
        assert body["ok"] is True
        return body["result"]

    async def ids(self, result: CaseResult, case_id: str) -> dict[str, str]:
        catalog = await self.catalog(result, case_id)
        branch = next(item for item in catalog["branches"] if item["name"] == "Koramangala Branch")
        appointment_type = next(
            item for item in catalog["appointment_types"] if item["name"] == "Dental Checkup"
        )
        practitioner = next(
            item
            for item in catalog["practitioners"]
            if item["display_name"] == "Dr. Ananya Rao"
        )
        return {
            "branch_id": branch["id"],
            "appointment_type_id": appointment_type["id"],
            "practitioner_id": practitioner["id"],
        }

    @staticmethod
    def next_scheduled_date(days_ahead: int = 7) -> date:
        candidate = datetime.now(UTC).date() + timedelta(days=days_ahead)
        while candidate.weekday() == 6:
            candidate += timedelta(days=1)
        return candidate

    async def patient_id(self, result: CaseResult, phone: str = "+91-98765-10001") -> str:
        body = await self.request(
            result,
            "lookup_patient",
            "GET",
            "/tools/patients/by-phone",
            expected={200},
            tool="lookup_patient",
            params={"phone": phone},
        )
        assert body["patients"]
        return body["patients"][0]["id"]

    async def slot(
        self,
        result: CaseResult,
        ids: dict[str, str],
        *,
        appointment_date: date | None = None,
        start_time: str | None = None,
        branch_id: str | None = None,
        practitioner_id: str | None = None,
        expected: set[int] | None = None,
    ) -> dict[str, Any]:
        body = await self.request(
            result,
            "search_availability",
            "POST",
            "/tools/search_availability",
            expected=expected or {200},
            tool="search_availability",
            json={
                "appointment_type_id": ids["appointment_type_id"],
                "branch_id": branch_id or ids["branch_id"],
                "practitioner_id": practitioner_id or ids["practitioner_id"],
                "appointment_date": (appointment_date or self.next_scheduled_date()).isoformat(),
                "start_time": start_time,
                "limit": 5,
            },
        )
        return body

    async def book(
        self, result: CaseResult, ids: dict[str, str], patient_id: str, slot: dict[str, Any], key: str
    ) -> dict[str, Any]:
        return await self.request(
            result,
            "create_appointment",
            "POST",
            "/tools/create_appointment",
            expected={201},
            tool="create_appointment",
            booking=True,
            headers={"Idempotency-Key": key},
            json={
                "patient_id": patient_id,
                "caller_full_name": "Rahul Verma",
                "practitioner_id": slot["practitioner_id"],
                "branch_id": slot["branch_id"],
                "appointment_type_id": ids["appointment_type_id"],
                "start_time": slot["start_time"],
                "notes": f"evaluation:{self.run_id}",
            },
        )


async def _booking_setup(harness: Harness, result: CaseResult) -> tuple[dict[str, str], str, dict[str, Any]]:
    ids = await harness.ids(result, result.case_id)
    patient_id = await harness.patient_id(result)
    availability = await harness.slot(result, ids)
    assert availability["slots"], "No seeded appointment slot was available."
    return ids, patient_id, availability["slots"][0]


async def _run_case(harness: Harness, definition: dict[str, Any]) -> CaseResult:
    result = CaseResult(case_id=definition["id"], scenario=definition["scenario"], success=False)
    scenario = definition["scenario"]
    try:
        if scenario == "shared_phone":
            body = await harness.request(result, "shared_phone_lookup", "GET", "/tools/patients/by-phone",
                expected={200}, tool="lookup_patient", params={"phone": "+91-98765-11111"})
            assert body["requires_disambiguation"] is True and body["match_count"] == 2
        elif scenario == "single_patient":
            body = await harness.request(result, "single_patient_lookup", "GET", "/tools/patients/by-phone",
                expected={200}, tool="lookup_patient", params={"phone": "+91-98765-10001"})
            assert body["requires_disambiguation"] is False and body["match_count"] == 1
        elif scenario == "earliest_slot":
            ids = await harness.ids(result, result.case_id)
            body = await harness.slot(result, ids)
            assert body["slots"] and body["slots"] == sorted(body["slots"], key=lambda slot: slot["start_time"])
        elif scenario in {"exact_time_booking", "idempotency_replay"}:
            ids, patient_id, chosen = await _booking_setup(harness, result)
            key = f"eval-{harness.run_id}-{result.case_id}-{uuid4()}"
            first = await harness.book(result, ids, patient_id, chosen, key)
            if scenario == "idempotency_replay":
                replay = await harness.request(
                    result, "idempotency_replay", "POST", "/tools/create_appointment", expected={201},
                    tool="create_appointment", booking=True, retry=True, headers={"Idempotency-Key": key},
                    json={
                        "patient_id": patient_id, "caller_full_name": "Rahul Verma",
                        "practitioner_id": chosen["practitioner_id"], "branch_id": chosen["branch_id"],
                        "appointment_type_id": ids["appointment_type_id"], "start_time": chosen["start_time"],
                        "notes": f"evaluation:{harness.run_id}",
                    },
                )
                assert replay["appointment_id"] == first["appointment_id"] and replay["idempotent_replay"] is True
        elif scenario in {"cancel", "reschedule"}:
            ids, patient_id, chosen = await _booking_setup(harness, result)
            created = await harness.book(result, ids, patient_id, chosen, f"eval-{harness.run_id}-{uuid4()}")
            if scenario == "cancel":
                body = await harness.request(result, "cancel_appointment", "POST",
                    f"/tools/appointments/{created['appointment_id']}/cancel", expected={200},
                    tool="cancel_appointment", booking=True, headers={"Idempotency-Key": f"eval-{uuid4()}"},
                    json={"caller_full_name": "Rahul Verma", "reason": "Evaluation cancellation"})
                assert body["status"] == "cancelled"
            else:
                later = await harness.slot(result, ids, appointment_date=harness.next_scheduled_date(14))
                assert later["slots"]
                body = await harness.request(result, "reschedule_appointment", "POST",
                    f"/tools/appointments/{created['appointment_id']}/reschedule", expected={200},
                    tool="reschedule_appointment", booking=True, headers={"Idempotency-Key": f"eval-{uuid4()}"},
                    json={"caller_full_name": "Rahul Verma", "practitioner_id": later["slots"][0]["practitioner_id"],
                          "branch_id": later["slots"][0]["branch_id"], "appointment_type_id": ids["appointment_type_id"],
                          "start_time": later["slots"][0]["start_time"]})
                assert body["appointment_id"] == created["appointment_id"]
        elif scenario == "language_lookup":
            call_id = harness.call_id(result.case_id)
            body = await harness.request(result, "voice_language_lookup", "POST", "/webhooks/retell/tools",
                expected={200}, tool="lookup_patient", json={"name": "lookup_patient",
                "args": {"phone": "+91-98765-10001", "utterance": definition["utterance"]},
                "call": {"call_id": call_id, "from_number": "+91-98765-10001", "language": definition["language"]}})
            assert body["ok"] is True
            context = await harness.request(result, "voice_language_context", "GET",
                f"/webhooks/retell/call-context/{call_id}", expected={200})
            assert context["language"] == definition["language"]
        elif scenario == "followup":
            patient_id = await harness.patient_id(result)
            call_id = harness.call_id(result.case_id)
            body = await harness.request(result, "create_followup", "POST", "/webhooks/retell/tools",
                expected={200}, tool="create_followup", json={"name": "create_followup",
                "args": {"patient_id": patient_id, "category": definition["category"], "notes": "Evaluation escalation"},
                "call": {"call_id": call_id, "from_number": "+91-98765-10001"}})
            assert body["ok"] is True and body["result"]["category"] == definition["category"]
        elif scenario == "double_booking":
            ids, patient_id, chosen = await _booking_setup(harness, result)
            payload = {"patient_id": patient_id, "caller_full_name": "Rahul Verma",
                       "practitioner_id": chosen["practitioner_id"], "branch_id": chosen["branch_id"],
                       "appointment_type_id": ids["appointment_type_id"], "start_time": chosen["start_time"],
                       "notes": f"evaluation:{harness.run_id}"}
            first, second = await asyncio.gather(
                harness.client.post("/tools/create_appointment", json=payload, headers={"Idempotency-Key": f"eval-{uuid4()}"}),
                harness.client.post("/tools/create_appointment", json=payload, headers={"Idempotency-Key": f"eval-{uuid4()}"}),
            )
            statuses = sorted([first.status_code, second.status_code])
            safe_rejection = (
                len(statuses) == 2
                and statuses.count(201) == 1
                and any(status in {409, 422} for status in statuses)
            )
            result.steps.append(StepResult("concurrent_double_booking", safe_rejection, 0, tool="create_appointment", booking_operation=True, detail=str(statuses)))
            assert safe_rejection, "Concurrent booking must create exactly one appointment."
        elif scenario in {"doctor_unavailable", "branch_unavailable", "outside_schedule"}:
            ids = await harness.ids(result, result.case_id)
            if scenario == "doctor_unavailable":
                body = await harness.slot(result, ids, appointment_date=harness.next_scheduled_date().replace(
                    day=harness.next_scheduled_date().day) + timedelta(days=(6 - harness.next_scheduled_date().weekday())))
                assert body["slots"] == []
            elif scenario == "branch_unavailable":
                body = await harness.slot(result, ids, branch_id=str(uuid4()), expected={404})
                assert "not found" in str(body).lower()
            else:
                body = await harness.slot(result, ids, start_time="20:00")
                assert body["slots"] == []
        elif scenario == "dropped_call":
            call_id = harness.call_id(result.case_id)
            ended = await harness.request(result, "call_ended_disconnected", "POST", "/webhooks/retell/call-ended",
                expected={200}, json={"call": {"call_id": call_id, "from_number": "+91-98765-10001",
                "call_status": "disconnected", "language": definition["language"]}})
            assert ended["disconnected"] is True
            context = await harness.request(result, "dropped_call_context", "GET",
                f"/webhooks/retell/call-context/{call_id}", expected={200})
            assert context["conversation_summary"]
        elif scenario == "resume_conversation":
            original = harness.call_id("dropped")
            resumed = harness.call_id("resumed")
            await harness.request(result, "disconnect_original", "POST", "/webhooks/retell/call-ended", expected={200},
                json={"call": {"call_id": original, "from_number": "+91-98765-10001", "call_status": "disconnected"}})
            await harness.request(result, "resume_lookup", "POST", "/webhooks/retell/tools", expected={200}, tool="lookup_patient",
                json={"name": "lookup_patient", "args": {"phone": "+91-98765-10001"},
                "call": {"call_id": resumed, "resumed_from_call_id": original, "from_number": "+91-98765-10001"}})
            context = await harness.request(result, "resumed_context", "GET",
                f"/webhooks/retell/call-context/{resumed}", expected={200})
            assert context["restored"] is True and context["resumed_from_retell_call_id"] == original
        else:
            raise ValueError(f"Unknown evaluation scenario: {scenario}")
        result.success = all(step.success for step in result.steps)
    except (AssertionError, httpx.HTTPError, KeyError, ValueError) as exc:
        result.failure = str(exc)
    return result


async def _cleanup(run_id: str) -> None:
    async with session_scope() as session:
        await session.execute(delete(IdempotencyKey).where(IdempotencyKey.key.like(f"eval-{run_id}%")))
        await session.execute(delete(Appointment).where(Appointment.notes == f"evaluation:{run_id}"))
        await session.execute(delete(Call).where(Call.retell_call_id.like(f"eval:{run_id}:%")))


async def main(cases_path: Path = CASES_PATH, output_dir: Path | None = None) -> dict[str, Any]:
    definitions = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]
    run_id = uuid4().hex[:12]
    await seed()
    transport = httpx.ASGITransport(app=app)
    results: list[CaseResult] = []
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://evaluation") as client:
            harness = Harness(client, run_id)
            for definition in definitions:
                results.append(await _run_case(harness, definition))
        report = build_report(results)
        write_reports(report, output_dir or Path(__file__).parent)
        return report
    finally:
        await _cleanup(run_id)
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent)
    arguments = parser.parse_args()
    report = asyncio.run(main(arguments.cases, arguments.output_dir))
    raise SystemExit(0 if report["summary"]["failed_cases"] == 0 else 1)
