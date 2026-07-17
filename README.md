# Care AI — Voice Receptionist for Sunrise Multispecialty Clinic

Live voice AI front desk that books, reschedules, and cancels appointments in **English**, **Hindi**, and mid-call **Hinglish** code-switching. Callers talk to **Maya**; tool calls hit a FastAPI backend backed by PostgreSQL (conflict-safe scheduling + durable call state) and a mock PMS write-back.

This README is the assignment write-up: what was built, why Retell, multilingual approach, latency numbers, how to run it, and known limits.

---

## Live demo


| Item | Value |
| --- | --- |
| **Live agent** | [Talk to Maya in Retell](https://agent.retellai.com/orb/agent_fbeb8e49d8f227d9916bb4b0d2?token=248c679dcc1b85db261db867a2676e3f) |
| **Live backend API** | [Swagger / OpenAPI](https://care-ai-backend-321k.onrender.com/docs) |
| **Mock PMS console** | [care-ai-pms.onrender.com](https://care-ai-pms.onrender.com/) |
| **Repository** | [github.com/SudhanshuAi/care-ai](https://github.com/SudhanshuAi/care-ai) |
| **Prompt** | [docs/prompts/SYSTEM_PROMPT.md](docs/prompts/SYSTEM_PROMPT.md) |
| **Manual call script** | [docs/LIVE_TEST_QUESTIONS.md](docs/LIVE_TEST_QUESTIONS.md) |
| **Retell setup** | [docs/retell/DASHBOARD_CONFIGURATION.md](docs/retell/DASHBOARD_CONFIGURATION.md) |
| **Bolna (optional adapter)** | [docs/bolna/README.md](docs/bolna/README.md) |


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
| **Delivery trade-off** | Bolna offers more component-level control, but Retell reduced integration work for telephony, interruption handling, multilingual voice configuration, and dashboard-managed tool calls. This left assignment time for durable scheduling state, live availability, and write-time conflict protection. |


**Bolna** remains in-repo only as a portability adapter over the same `/tools`
services (`docs/bolna/`). It is not a second deployed agent. **Retell is the
only configured and callable voice platform for this submission.**

**Other stack picks**


| Layer   | Choice                              | Why                                                                        |
| ------- | ----------------------------------- | -------------------------------------------------------------------------- |
| LLM     | Retell LLM (configured in dashboard) | Dashboard-configurable bilingual conversation model for the live agent |
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



## Evaluation and latency

The evaluation harness measures the real FastAPI routes, Retell adapter, PostgreSQL
constraints, and mock PMS behavior. It is **not** an end-to-end spoken-latency test.
Run it from a clean clone to generate a timestamped report for the environment being
reviewed; reports are intentionally gitignored rather than presenting stale numbers.

**How to read the results:** backend tool latency is distinct from spoken latency,
which also includes ASR, LLM first-token time, TTS, telephony, and network time.
Holding phrases and Retell “speak during execution” reduce perceived wait time while
tools run.

**Component breakdown (production voice path):**


| Component                     | Where measured                                                      |
| ----------------------------- | ------------------------------------------------------------------- |
| Tool / DB / PMS               | This harness + structured request logs (`latency_ms`)               |
| ASR, LLM TTFT, TTS, telephony | Retell analytics / call recordings (not inventable from HTTP times) |


**False confidence in the harness:** it proves scheduling correctness, idempotency,
conflict rejection, language metadata on tools, and drop-resume state. It does **not**
grade spoken Hindi grammar, barge-in feel, or turns-to-booking on a live call. Run it
only against the dedicated evaluation database:

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



## Reviewer quick start (clean clone)

**Requirements:** Docker Desktop / Docker Compose. No Retell, Bolna, or cloud-database
credentials are needed to run the backend locally.

### Windows PowerShell

```powershell
git clone <YOUR_REPOSITORY_URL> care-ai
cd care-ai
.\verify-clone.ps1
```

The script creates a local `.env` from `.env.example`, refuses to use an untracked
Compose override or a non-local database URL, builds the stack, waits for readiness,
seeds the clinic, then runs lint and the test suite.

### macOS / Linux or manual setup

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec backend python -m scripts.seed_clinic
curl http://localhost:8000/health/ready
docker compose exec backend ruff check .
docker compose exec backend pytest -q
```

OpenAPI is available at `http://localhost:8000/docs`. To run the isolated evaluation
harness, follow [backend/evaluation/README.md](backend/evaluation/README.md).

### Live voice setup

For a callable demo, deploy the backend behind public HTTPS, add the provider secrets
to that deployment environment, then follow
[docs/retell/DASHBOARD_CONFIGURATION.md](docs/retell/DASHBOARD_CONFIGURATION.md).
The current live demo is available through the Retell web link above. Provision and
bind a Retell phone number separately if the reviewer must test by telephone. Use
[docs/LIVE_TEST_QUESTIONS.md](docs/LIVE_TEST_QUESTIONS.md) for the reviewer call script.

Unit/integration tests cover adapters, guardrails, PMS sync, and conversation resume.
Tool contract details: [docs/TOOL_API.md](docs/TOOL_API.md).

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
5. The submitted Retell web link is callable in a browser. A separate live phone
   number is still required if reviewers insist on testing through PSTN.

---



## Repository map

```text
backend/           FastAPI app, adapters, services, Alembic, tests, evaluation
frontend/          Mock PMS admin console (deploy separately on Render)
docs/prompts/      Production system prompt
docs/retell/       Agent config + Custom Function JSON + testing notes
docs/bolna/        Optional Bolna adapter docs + tool JSON
docs/TOOL_API.md   REST tool contract
docker-compose.yml Postgres + backend
```

### Mock PMS admin UI

Live: [https://care-ai-pms.onrender.com/](https://care-ai-pms.onrender.com/)  
Source: [`frontend/`](frontend/README.md)

It calls:

- `GET /admin/pms/appointments`
- `GET /admin/pms/appointments/{id}`
- `GET /admin/pms/receipts`
- `POST /admin/pms/appointments/{id}/retry`

Backend `CORS_ORIGINS` must include `https://care-ai-pms.onrender.com`. No admin token is required for this demo console.
