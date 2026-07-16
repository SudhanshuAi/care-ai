"""Smoke-test backend API endpoints (local or deployed).

Usage:
    python -m scripts.test_deployed_api
    python -m scripts.test_deployed_api --base-url https://care-ai-backend-321k.onrender.com
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings


@dataclass
class Result:
    name: str
    ok: bool
    status: int
    detail: str = ""


def record(results: list[Result], name: str, ok: bool, status: int, detail: str = "") -> None:
    results.append(Result(name=name, ok=ok, status=status, detail=detail))
    mark = "PASS" if ok else "FAIL"
    suffix = f" | {detail}" if detail else ""
    print(f"[{mark}] {name} -> HTTP {status}{suffix}")


def sign_retell_body(raw_body: bytes, api_key: str, timestamp_ms: int | None = None) -> str:
    timestamp_ms = timestamp_ms or int(time.time() * 1000)
    digest = hmac.new(
        api_key.encode("utf-8"),
        raw_body + str(timestamp_ms).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"v={timestamp_ms},d={digest}"


def fetch_catalog_ids(client: httpx.Client, api_key: str | None) -> tuple[str, str]:
    payload = {"name": "get_clinic_catalog", "args": {}}
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Retell-Signature"] = sign_retell_body(raw_body, api_key)
    response = client.post("/webhooks/retell/tools", content=raw_body, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(
            f"get_clinic_catalog failed: HTTP {response.status_code} {response.text[:200]}"
        )
    catalog = response.json()["result"]
    branch = next(
        (item for item in catalog["branches"] if "Koramangala" in item["name"]),
        catalog["branches"][0],
    )
    appointment_type = next(
        (item for item in catalog["appointment_types"] if "Dental" in item["name"]),
        catalog["appointment_types"][0],
    )
    return appointment_type["id"], branch["id"]


def run(base_url: str) -> int:
    results: list[Result] = []
    settings = get_settings()
    patient_id: str | None = None
    appointment_type_id: str | None = None
    branch_id: str | None = None
    appointment_id: str | None = None

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        r = client.get("/health/live")
        record(
            results,
            "GET /health/live",
            r.status_code == 200 and r.json().get("status") == "ok",
            r.status_code,
        )

        r = client.get("/health/ready")
        body = r.json() if r.status_code == 200 else {}
        record(
            results,
            "GET /health/ready",
            r.status_code == 200 and body.get("database") == "connected",
            r.status_code,
        )

        r = client.get("/tools/patients/by-phone", params={"phone": "+91-98765-10001"})
        body = r.json() if r.status_code == 200 else {}
        ok = r.status_code == 200 and body.get("match_count") == 1
        if ok:
            patient_id = body["patients"][0]["id"]
        record(results, "GET /tools/patients/by-phone", ok, r.status_code, f"patient_id={patient_id}")

        try:
            appointment_type_id, branch_id = fetch_catalog_ids(client, settings.retell_api_key)
            record(
                results,
                "POST /webhooks/retell/tools (get_clinic_catalog)",
                True,
                200,
                f"branch_id={branch_id}",
            )
        except Exception as exc:
            record(results, "POST /webhooks/retell/tools (get_clinic_catalog)", False, 0, str(exc))
            return _summarize(results)

        if not patient_id:
            record(results, "Booking flow", False, 0, "missing patient_id")
            return _summarize(results)

        target_date = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
        r = client.post(
            "/tools/search_availability",
            json={
                "appointment_type_id": appointment_type_id,
                "branch_id": branch_id,
                "appointment_date": target_date,
                "limit": 5,
            },
        )
        slots = r.json().get("slots", []) if r.status_code == 200 else []
        record(
            results,
            "POST /tools/search_availability",
            r.status_code == 200 and len(slots) > 0,
            r.status_code,
            f"slots={len(slots)}",
        )
        if not slots:
            return _summarize(results)

        slot = slots[0]
        create_key = f"api-test-create-{uuid.uuid4()}"
        payload = {
            "patient_id": patient_id,
            "caller_full_name": "Rahul Verma",
            "practitioner_id": slot["practitioner_id"],
            "branch_id": slot["branch_id"],
            "appointment_type_id": appointment_type_id,
            "start_time": slot["start_time"],
        }
        r = client.post(
            "/tools/create_appointment",
            json=payload,
            headers={"Idempotency-Key": create_key},
        )
        body = r.json() if r.status_code == 201 else {}
        ok = r.status_code == 201 and body.get("status") == "booked"
        if ok:
            appointment_id = body["appointment_id"]
        record(results, "POST /tools/create_appointment", ok, r.status_code, f"id={appointment_id}")

        alternate = next((s for s in slots if s["start_time"] != slot["start_time"]), None)
        if appointment_id and alternate:
            r = client.post(
                f"/tools/appointments/{appointment_id}/reschedule",
                json={
                    "caller_full_name": "Rahul Verma",
                    "practitioner_id": alternate["practitioner_id"],
                    "branch_id": alternate["branch_id"],
                    "appointment_type_id": appointment_type_id,
                    "start_time": alternate["start_time"],
                },
                headers={"Idempotency-Key": f"api-test-reschedule-{uuid.uuid4()}"},
            )
            body = r.json() if r.status_code == 200 else {}
            record(
                results,
                "POST /tools/appointments/{id}/reschedule",
                r.status_code == 200 and body.get("status") == "booked",
                r.status_code,
                f"start={body.get('start_time')}",
            )
        else:
            record(results, "POST /tools/appointments/{id}/reschedule", False, 0, "no alternate slot")

        if appointment_id:
            r = client.post(
                f"/tools/appointments/{appointment_id}/cancel",
                json={
                    "caller_full_name": "Rahul Verma",
                    "reason": "API verification test",
                },
                headers={"Idempotency-Key": f"api-test-cancel-{uuid.uuid4()}"},
            )
            body = r.json() if r.status_code == 200 else {}
            fee = body.get("cancellation_fee") or {}
            record(
                results,
                "POST /tools/appointments/{id}/cancel",
                r.status_code == 200 and body.get("status") == "cancelled",
                r.status_code,
                f"fee_applicable={fee.get('applicable')}",
            )

    return _summarize(results)


def _summarize(results: list[Result]) -> int:
    passed = sum(1 for item in results if item.ok)
    failed = [item for item in results if not item.ok]
    print()
    print(f"Summary: {passed}/{len(results)} passed")
    if failed:
        print("Failures:")
        for item in failed:
            print(f"  - {item.name}: {item.detail or item.status}")
    return 0 if not failed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL",
    )
    args = parser.parse_args()
    raise SystemExit(run(args.base_url.rstrip("/")))


if __name__ == "__main__":
    main()
