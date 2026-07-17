# Backend Tool API

The endpoints below are implemented as regular REST tools. They have no
Retell dependency, prompt, WebSocket, or voice-specific code. OpenAPI
examples are available interactively at `http://localhost:8000/docs`.

## Run locally

```bash
docker compose up --build -d
docker compose exec backend python -m scripts.seed_clinic
docker compose exec backend pytest -q
```

The seed script is safe to run again; it does not duplicate clinic data and
ensures the marked future demo appointments remain available for cancellation
and reschedule testing.

## Patient lookup

```bash
curl --get "http://localhost:8000/tools/patients/by-phone" \
  --data-urlencode "phone=+91-98765-11111"
```

The seeded phone number belongs to Arjun and Kavya Mehta. The response
returns both records and `requires_disambiguation: true`, instead of
guessing a patient.

```bash
curl --get "http://localhost:8000/tools/patients/by-name" \
  --data-urlencode "name=Rahul"
```

## Availability

Get IDs from Swagger or PostgreSQL, then search the live database:

```bash
curl -X POST "http://localhost:8000/tools/search_availability" \
  -H "Content-Type: application/json" \
  -d '{
    "appointment_type_id": "APPOINTMENT_TYPE_UUID",
    "branch_id": "BRANCH_UUID",
    "appointment_date": "YYYY-MM-DD",
    "start_time": "09:00:00",
    "end_time": "17:00:00",
    "earliest_only": true
  }'
```

The engine reads `practitioner_schedules` and live `appointments` on
every request. It does not cache results.

## Create an appointment

The timestamp must include an offset or `Z`; the patient name is
mandatory, even when the patient ID is already known.

```bash
curl -X POST "http://localhost:8000/tools/create_appointment" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: booking-example-001" \
  -d '{
    "patient_id": "PATIENT_UUID",
    "caller_full_name": "Rahul Verma",
    "practitioner_id": "PRACTITIONER_UUID",
    "branch_id": "BRANCH_UUID",
    "appointment_type_id": "APPOINTMENT_TYPE_UUID",
    "start_time": "YYYY-MM-DDT09:00:00+05:30"
  }'
```

Repeat the exact request with the same `Idempotency-Key` to get the
original confirmation with `idempotent_replay: true`; reuse the key
with a different payload returns HTTP 409.

## Reschedule and cancel

```bash
curl -X POST "http://localhost:8000/tools/appointments/APPOINTMENT_UUID/reschedule" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: reschedule-example-001" \
  -d '{
    "caller_full_name": "Rahul Verma",
    "practitioner_id": "PRACTITIONER_UUID",
    "branch_id": "BRANCH_UUID",
    "appointment_type_id": "APPOINTMENT_TYPE_UUID",
    "start_time": "YYYY-MM-DDT10:00:00+05:30"
  }'

curl -X POST "http://localhost:8000/tools/appointments/APPOINTMENT_UUID/cancel" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: cancel-example-001" \
  -d '{
    "caller_full_name": "Rahul Verma",
    "reason": "Cannot attend"
  }'
```

Both responses expose `cancellation_fee.applicable`. A fee amount is
only returned inside the appointment type's configured fee window.

## Human callback / clinical concern

```bash
curl -X POST "http://localhost:8000/tools/followups" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "CALL_UUID",
    "patient_id": "PATIENT_UUID",
    "category": "human_requested",
    "notes": "Caller asked for a human callback."
  }'
```

Valid categories are `human_requested`, `clinical_concern`, and
`other`.
