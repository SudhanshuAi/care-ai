# Retell Integration — Testing Instructions

## A. Backend readiness

```bash
docker compose up --build -d
docker compose exec backend python -m scripts.seed_clinic
curl http://localhost:8000/health/ready
```

Expect: `{"status":"ok","database":"connected"}`.

## B. Expose the webhook locally

```bash
# example
ngrok http 8000
```

Set `BACKEND_BASE_URL` to the ngrok HTTPS URL when creating Retell functions.

## C. Simulate a Retell tool call (no signature)

With `RETELL_API_KEY` unset / `RETELL_VERIFY_SIGNATURES=false` locally:

```bash
curl -X POST "http://localhost:8000/webhooks/retell/tools" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "lookup_patient",
    "args": { "phone": "+91-98765-11111" },
    "call": {
      "call_id": "test_call_001",
      "from_number": "+91-98765-11111",
      "direction": "inbound"
    }
  }'
```

Expect `requires_disambiguation: true` and both Mehta patients.

Catalog:

```bash
curl -X POST "http://localhost:8000/webhooks/retell/tools" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_clinic_catalog",
    "args": {},
    "call": { "call_id": "test_call_001", "from_number": "+91-98765-10001" }
  }'
```

Availability (replace UUIDs from catalog):

```bash
curl -X POST "http://localhost:8000/webhooks/retell/tools" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_availability",
    "args": {
      "appointment_type_name": "Dental Checkup",
      "branch_name": "Koramangala",
      "appointment_date": "2026-07-16",
      "earliest_only": true
    },
    "call": { "call_id": "test_call_001", "from_number": "+91-98765-10001" }
  }'
```

## D. Dashboard live call checklist

Configure the agent using [DASHBOARD_CONFIGURATION.md](DASHBOARD_CONFIGURATION.md), then call the Retell number and verify:

1. **Opening** — bilingual-capable greeting; language mirrors caller.
2. **Shared phone** — call from `+91-98765-11111` (or look up that phone); agent asks for name before booking.
3. **Live availability** — ask for a time, then change it; agent re-checks (second tool call), does not invent from memory.
4. **Earliest slot** — “earliest available tomorrow”; agent searches across eligible doctors/branches.
5. **Confirm before book** — agent restates branch/doctor/date/time, then books.
6. **Name required** — booking includes caller full name.
7. **AI honesty** — “Are you a bot?” → honest answer, offer to continue or callback.
8. **Human request** — “I need to talk to someone” → `create_followup`, promise of callback only.
9. **Interruption** — talk over the agent mid-sentence; agent stops and follows your new input.
10. **Hindi / code-switch** — try pure Hindi and a mixed sentence; responses stay natural.

## E. Automated unit tests

```bash
docker compose exec backend pytest -q tests/unit/test_retell_security.py tests/unit/test_retell_dispatcher.py
```

## F. What is not covered by this live-call checklist

- The isolated backend evaluation harness; run
  [`backend/evaluation/README.md`](../../backend/evaluation/README.md) for
  scheduling and tool-route metrics.
- Custom LLM WebSocket orchestrator (optional upgrade path)
- Live Cliniko write-back
- Production phone number provisioning for you (must be done in your Retell account)
