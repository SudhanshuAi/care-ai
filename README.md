# Care AI — Voice Receptionist for Sunrise Multispecialty Clinic

Live voice AI front desk that books, reschedules, and cancels appointments in **English**, **Hindi**, and mid-call **Hinglish** code-switching. Callers talk to **Maya**; tool calls hit a FastAPI backend backed by PostgreSQL (conflict-safe scheduling + durable call state) and a mock PMS write-back.

This README is the assignment write-up: what was built, why Retell, multilingual approach, latency numbers, how to run it, and known limits.

---

## Live demo


| Item                         | Value                                                                              |
| ---------------------------- | ---------------------------------------------------------------------------------- |
| **Test phone number**        | *{}*                                                                               |
| **Prompt**                   | `[docs/prompts/SYSTEM_PROMPT.md](docs/prompts/SYSTEM_PROMPT.md)`                   |
| **Retell setup**             | `[docs/retell/DASHBOARD_CONFIGURATION.md](docs/retell/DASHBOARD_CONFIGURATION.md)` |
| **Bolna (optional adapter)** | `[docs/bolna/README.md](docs/bolna/README.md)`                                     |


The production agent is **Retell LLM + Custom Functions** → `POST /webhooks/retell/tools` → shared scheduling services. Bolna is wired to the same services for portability; the live stack choice below is Retell.

---



## What we built



### Agent (Maya)

- Full appointment lifecycle: lookup → live availability → book / reschedule / cancel
- Shared-phone disambiguation by name; never books anonymously
- Dropped-call / callback resume from durable Postgres call state (not LLM memory alone)
- Escalation via `create_followup` (human request or clinical concern) with callback expectation, not fake live transfer
- Prompt + few-shots: `[docs/prompts/SYSTEM_PROMPT.md](docs/prompts/SYSTEM_PROMPT.md)`



### Clinic data

- **Sunrise Multispecialty Clinic** (Asia/Kolkata, INR)
- **Two branches:** Koramangala and Indiranagar
- Departments: Dentistry, Physiotherapy, Dermatology, Pediatrics — with practitioners, weekly schedules, buffers, and sample patients
- Seeded via `python -m scripts.seed_clinic` (see limitations on data provenance)



### Backend

- FastAPI tool APIs (`/tools/*`) with no voice-SDK coupling — see `[docs/TOOL_API.md](docs/TOOL_API.md)`
- Thin Retell + Bolna webhook adapters over the same dispatcher / services
- PostgreSQL source of truth with **DB-level** practitioner and patient overlap exclusion (`EXCLUDE … gist`)
- Live availability on every search (no cached slot answers); offered slots guarded before confirm
- Idempotent mutating tools (`Idempotency-Key`) + mock PMS write-back with retry / sync status



### Eval harness

- Multi-scenario runner against real routes + Retell adapter + Postgres (not mocked scheduling logic)
- Metrics per language case (en-IN / hi-IN / hi-en) and backend latency breakdown
- Re-runnable from a clean clone — `[backend/evaluation/README.md](backend/evaluation/README.md)`

---



## Stack choice: Retell (with Bolna adapter kept)

Assignment requires **one** platform fully live. **Primary / live: Retell AI.**


| Factor                 | Why Retell won for this clinic                                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Telephony**          | Managed numbers + PSTN without owning SIP/carrier ops in a short build window                                                                          |
| **Interruption / VAD** | Built-in barge-in; we tune medium–high sensitivity + prompt rules to stop cleanly                                                                      |
| **Multilingual**       | Multilingual STT + ElevenLabs TTS via Retell; language mode `auto` — no translation dictionary                                                         |
| **Tool calling**       | Custom Functions POST to our signed webhook; we own idempotency, state, and DB writes                                                                  |
| **Latency UX**         | “Speak during execution” + prompt holding phrases mask tool round-trips                                                                                |
| **Cost trade-off**     | Bolna is typically cheaper per minute and more self-hostable, but ops cost for STT/TTS/telephony outweighed that for a production-callable clinic demo |


**Bolna** remains in-repo as a second adapter over the same `/tools` services (`docs/bolna/`). Use it if you prefer Bolna’s dashboard; do not treat dual adapters as dual live agents unless both numbers are configured.

**Other stack picks**


| Layer   | Choice                              | Why                                                                        |
| ------- | ----------------------------------- | -------------------------------------------------------------------------- |
| LLM     | Retell-hosted GPT-4o (Retell LLM)   | Strong bilingual generation; dashboard-configurable for a live number fast |
| Backend | Python + FastAPI (async)            | Clean tool schemas (Pydantic) + async DB + ASGI eval harness               |
| DB      | PostgreSQL + SQLAlchemy 2 + Alembic | Write-time double-booking prevention that holds under concurrency          |
| State   | Postgres `calls` rows               | Drop-resume and returning-caller context survive restarts (no Redis)       |
| PMS     | Mock PMS adapter (default)          | Assignment-required write-back with idempotency; clinic seed is separate   |


---



## Multilingual approach

No hardcoded phrase tables.

1. **ASR / TTS:** Retell multilingual STT + ElevenLabs multilingual voice (`language: multi`, auto detection) — see `[docs/retell/agent_config.json](docs/retell/agent_config.json)`.
2. **LLM behavior:** Prompt instructs Maya to **mirror** the caller’s language/register every turn (English / Hindi / Hinglish), not switch spontaneously, and to keep names/branches natural.
3. **Backend:** Language tags (`en-IN`, `hi-IN`, `hi-en`) are stored on call state and asserted in the eval harness language cases. The backend does not translate; it schedules.

---



## Architecture

```text
Caller phone
    → Retell (ASR / VAD / TTS / telephony)
        → Retell LLM + Custom Functions
            → POST /webhooks/retell/tools  (signature-verified)
                → services (patient, availability, appointment, followup, conversation state)
                    → PostgreSQL
                    → Mock PMS write-back (after confirmed booking)
```

Hard guarantees live in the backend/DB (conflicts, idempotency, resume state, live availability). The prompt handles conversational quality and language mirroring.

---



## Latency numbers

Measured with the in-repo eval harness (ASGI round-trip against real FastAPI + Postgres + Retell tool adapter). **Not** end-to-end spoken latency.


| Metric                         | Value (local Docker run)          |
| ------------------------------ | --------------------------------- |
| Conversation success rate      | **94.4%** (17 / 18 cases)         |
| Booking accuracy               | **100%**                          |
| Tool accuracy                  | **97.6%**                         |
| Average tool latency           | **~37 ms**                        |
| Average booking latency        | **~58 ms**                        |
| Average response latency       | **~35 ms**                        |
| Average TTFT (ASR→first audio) | **not collected** in this harness |


**How to read these numbers:** backend tool latency is intentionally small so spoken latency is dominated by provider ASR + LLM + TTS + network. Holding phrases and Retell “speak during execution” exist so callers hear natural fill while tools run.

**Component breakdown (production voice path):**


| Component                     | Where measured                                                      |
| ----------------------------- | ------------------------------------------------------------------- |
| Tool / DB / PMS               | This harness + structured request logs (`latency_ms`)               |
| ASR, LLM TTFT, TTS, telephony | Retell analytics / call recordings (not inventable from HTTP times) |


**False confidence in the harness:** it proves scheduling correctness, idempotency, conflict rejection, language metadata on tools, and drop-resume state. It does **not** grade spoken Hindi grammar, barge-in feel, or turns-to-booking on a live call. Re-run after clone:

```powershell
# Create an isolated DB, migrate it, then run (from host with Docker up)
docker compose exec db psql -U careai -d postgres -c "CREATE DATABASE careai_evaluation;"
docker compose exec -e DATABASE_URL=postgresql+asyncpg://careai:careai_dev_password@db:5432/careai_evaluation backend alembic upgrade head
docker compose exec `
  -e DATABASE_URL=postgresql+asyncpg://careai:careai_dev_password@db:5432/careai `
  -e EVALUATION_DATABASE_URL=postgresql+asyncpg://careai:careai_dev_password@db:5432/careai_evaluation `
  -e RETELL_VERIFY_SIGNATURES=false `
  backend python -m evaluation.runner
```

Reports write under `backend/evaluation/` and are gitignored.

---



## Required scenarios → mechanisms


| Scenario                                                 | Mechanism                                                               |
| -------------------------------------------------------- | ----------------------------------------------------------------------- |
| Underspecified times (“Thursday morning”, “around 4:30”) | Prompt + live `search_availability` every preference change             |
| Returning patient                                        | `lookup_patient` by phone/name; shared line → disambiguate              |
| Missed outbound / callback + dropped call                | Durable call state; resume from last `disconnected` call for the number |
| Stale availability                                       | No availability cache; re-search before offer/book                      |
| Earliest across branches/practitioners                   | `earliest_only` search over live schedules + bookings                   |
| Branch-specific specialty                                | Catalog + branch-scoped search against DB                               |
| Double-book / race                                       | Postgres exclusion constraints + application checks + offer guardrails  |
| Human / clinical escalation                              | `create_followup` + honest callback language                            |


---



## Quick start (reviewer clone)

**Requirements:** Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec backend python -m scripts.seed_clinic
curl http://localhost:8000/health/live
# OpenAPI: http://localhost:8000/docs
docker compose exec backend pytest -q
```

Wire a public HTTPS URL (ngrok / Render / etc.) into Retell Custom Functions using `[docs/retell/](docs/retell/)`. Paste `[docs/prompts/SYSTEM_PROMPT.md](docs/prompts/SYSTEM_PROMPT.md)` into the Retell LLM general prompt. Assign a phone number and call it.

Unit/integration tests cover adapters, guardrails, PMS sync, and conversation resume. Tool contract details: `[docs/TOOL_API.md](docs/TOOL_API.md)`.

---



## Prompt and prompt logic

Single production prompt: `[docs/prompts/SYSTEM_PROMPT.md](docs/prompts/SYSTEM_PROMPT.md)`.

Design intent:

- Mirror language; never invent availability or IDs
- Ask only for the next missing field; resume instead of restarting
- Always confirm full name before mutating appointments
- Re-run availability when preferences change
- Hold phrase once while tools run; stop immediately on barge-in
- Escalate honestly via follow-up, not fake transfer

---



## Known limitations

1. **Spoken E2E latency / TTFT** are not measured in the offline harness; use Retell call analytics for ASR/LLM/TTS.
2. **Clinic seed** is a realistic two-branch Bengaluru dataset for demos; replace with a Cliniko (or other PMS) export if you need strictly third-party-sourced practitioners.
3. **LLM brain** is Retell-hosted (not a custom LLM WebSocket orchestrator). Conversation *state* that must not be forgotten still lives in Postgres.
4. **Eval language cases** assert metadata and tool paths, not spoken fluency.
5. One harness case (`branch_unavailable`) currently fails when given a non-existent branch id (404) — expected “no slots” vs not-found semantics can be tightened.
6. Live phone number must be provisioned in Retell and filled into the table at the top of this README before email submission.

---



## Repository map

```text
backend/           FastAPI app, adapters, services, Alembic, tests, evaluation
docs/prompts/      Production system prompt
docs/retell/       Agent config + Custom Function JSON + testing notes
docs/bolna/        Optional Bolna adapter docs + tool JSON
docs/TOOL_API.md   REST tool contract
docker-compose.yml Postgres + backend
```

