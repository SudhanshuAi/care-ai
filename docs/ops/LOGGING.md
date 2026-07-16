# Production logging & correlation

Structured logging is implemented with **structlog** on top of the stdlib
logger. Local/dev defaults to colored console lines; staging and production
should emit **one JSON object per line**.

## Enable JSON logs

```bash
LOG_LEVEL=INFO
JSON_LOGS=true
```

Set these in the process environment (see `backend/.env.example`). When
`JSON_LOGS=true`, every event is rendered with `structlog.processors.JSONRenderer`.

## Correlation model

| Field | Scope | Source |
|---|---|---|
| `request_id` | Single HTTP request | `X-Request-ID` (generated if absent) |
| `call_id` | Current Retell/Bolna call session | Provider call payload |
| `conversation_id` | Entire booking conversation across reconnects | Root `Call.id` in the resume chain |
| `database_call_id` | Current DB `calls` row | `Call.id` |
| `provider` | Adapter surface | Path (`retell` / `bolna` / `rest`) |

`request_id` is always present on HTTP traffic and is echoed as the
`X-Request-ID` response header.

Voice tool responses also echo:

- `X-Call-ID` — provider call id
- `X-Conversation-ID` — stable conversation correlation id

Filter an interrupted booking by `conversation_id` to see every tool
invocation before and after the caller redialed.

## Field dictionary

These fields appear on Retell tool events and (when known) ride along on
nested logs via contextvars:

| Field | Meaning |
|---|---|
| `call_id` | Provider call id (Retell `call.call_id`) |
| `conversation_id` | Root call UUID spanning resumes |
| `patient_id` | Identified / requested patient |
| `appointment_id` | From tool args or booking result |
| `tool_name` | Custom function name |
| `latency_ms` | Tool or HTTP duration |
| `language` | Call language (e.g. `en-IN`, `hi-IN`) |
| `status` | `started` / `ok` / `error` / `completed` / `disconnected` |
| `provider` | `retell`, `bolna`, or `rest` |
| `conversation_state` | Compact memory snapshot (`current_intent`, `last_tool_called`, flags) |
| `exception_type` | Exception class name on failures |

HTTP access lines (`http_request`) always include `request_id`, `provider`,
`method`, `path`, `status_code`, `status`, `latency_ms`, and
`exception_type` when an unhandled exception escaped the handler.

## Voice tool and PMS events

Every Retell or Bolna custom-function invocation emits provider-specific events:

1. `<provider>_tool_invoked` — `status=started`
2. `<provider>_tool_completed` — `status=ok|error`, with `latency_ms`

Failures also emit `<provider>_tool_domain_error` or
`<provider>_tool_argument_error` with `exception_type` and `detail` before
the completion event.

PMS write-back emits:

- `pms_sync_succeeded` — durable mock-PMS receipt created or replayed
- `pms_sync_failed` — booking remains confirmed; retry state is recorded
- `pms_reconciliation_complete` — retry worker summary

Call lifecycle:

- `retell_call_ended` — terminal webhook with `status=completed|disconnected`
- `retell_call_ended_ignored` — payload missing `call_id`

## Example JSON line

```json
{
  "event": "retell_tool_completed",
  "tool_name": "create_appointment",
  "call_id": "retell_abc123",
  "conversation_id": "a10bc9e8-94ad-4e9e-a1a3-d69a4ad0aafc",
  "patient_id": "b6a2ee72-cbfd-4fb7-95c4-b468dc5f9a3f",
  "appointment_id": "…",
  "language": "en-IN",
  "provider": "retell",
  "status": "ok",
  "latency_ms": 182.4,
  "request_id": "7a888c18-2049-4757-b6f8-d94158ddf923",
  "conversation_state": {
    "current_intent": "appointment_confirmed",
    "last_tool_called": "create_appointment",
    "has_pending_confirmation": false,
    "has_availability_search": true,
    "call_status": "in_progress"
  },
  "level": "info",
  "timestamp": "2026-07-16T18:30:00.000000Z"
}
```

## Related surfaces

- Prometheus scrape: `GET /metrics`
- Aggregated ops views: `GET /admin/metrics`, `GET /admin/dashboard`
- Call memory inspection: `GET /webhooks/retell/call-context/{call_id}`

Implementation entry points:

- `backend/app/core/logging.py` — JSON vs console renderer
- `backend/app/core/middleware.py` — `request_id` + HTTP access log
- `backend/app/core/observability.py` — conversation field helpers
- `backend/app/adapters/retell/dispatcher.py` — per-tool structured events
