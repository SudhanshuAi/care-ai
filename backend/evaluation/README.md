# Backend Evaluation Harness

This harness evaluates the real FastAPI routes, Retell tool adapter, services,
repositories, and PostgreSQL constraints. It does not mock scheduling business
logic and does not place a live voice call.

## Safety

Use an isolated database. The runner refuses to start unless
`EVALUATION_DATABASE_URL` is set and differs from `DATABASE_URL`.

```powershell
cd backend
$env:EVALUATION_DATABASE_URL = "postgresql+asyncpg://careai:careai_dev_password@localhost:5432/careai_evaluation"
$env:RETELL_VERIFY_SIGNATURES = "false"
alembic upgrade head
python -m evaluation.runner
```

`RETELL_VERIFY_SIGNATURES=false` is appropriate only for this isolated,
in-process evaluation. Do not run the harness against production, staging, or
a shared developer database.

The runner seeds the clinic dataset, uses a unique run identifier for every
mutation, and removes its appointments, calls, follow-ups (through call
cascades), and idempotency keys when it finishes.

## Outputs

The default output directory is this folder:

- `evaluation_report.json`: complete machine-readable results and per-step
  timings.
- `evaluation_report.md`: review-friendly summary.
- `evaluation_summary.csv`: one row per scenario.

Pass `--output-dir <path>` to write artifacts elsewhere. These generated files
are intentionally not source-controlled.

## Coverage

`cases.json` contains the requested shared-phone, single-patient, availability,
booking, cancellation, rescheduling, language, escalation, conflict,
idempotency, unavailable schedule, dropped-call, and call-resume scenarios.
Cases use dynamic future weekdays and live availability results, so they do not
depend on stale fixed timestamps.

Hindi, English, and code-switch cases validate that language metadata survives
the real voice-tool webhook and conversation-state path. They cannot grade
spoken grammar or language mirroring because this repository currently uses
provider-hosted LLM/TTS and exposes no programmable voice-call/streaming API.

## Metrics

| Metric | Definition |
|---|---|
| Conversation success rate | Passing scenarios divided by all scenarios |
| Booking accuracy | Passing create/cancel/reschedule/conflict operations divided by booking operations |
| Tool accuracy | Passing tool-route steps divided by tool-route steps |
| Average tool latency | ASGI request round-trip for tool calls |
| Average booking latency | ASGI request round-trip for mutating appointment calls |
| Average response latency | ASGI request round-trip across all harness requests |
| Average retries | Explicit idempotency replay attempts per scenario |
| Failures | Failed case ID, scenario, and assertion detail |

`average_ttft_ms` is always `null` with a `not_collected` explanation. It must
not be inferred from HTTP latency: true TTFT and spoken response latency need
Retell/Bolna analytics or a backend-owned LLM/TTS streaming orchestrator.
