# Retell Dashboard Configuration

This milestone wires **Retell AI** to the existing Care AI backend without changing `/tools/*` REST contracts. Retell Custom Functions POST to a thin adapter:

`POST {{BACKEND_BASE_URL}}/webhooks/retell/tools`

The adapter translates `{ name, args, call }` into the same services the REST layer uses, injects `Idempotency-Key` for mutating calls, and upserts `Call` rows for follow-ups.

## Artifacts in this folder

| File | Purpose |
|---|---|
| [agent_config.json](agent_config.json) | High-level agent / voice / STT / TTS / interruption settings |
| [tools/*.json](tools/) | One Retell Custom Function definition per tool |
| [../prompts/SYSTEM_PROMPT.md](../prompts/SYSTEM_PROMPT.md) | Production system prompt |
| [TESTING.md](TESTING.md) | End-to-end testing checklist |
| [CONVERSATION_MEMORY.md](CONVERSATION_MEMORY.md) | Durable call state and reconnect behavior |

## 1. Prerequisites

1. Backend reachable on a public HTTPS URL (ngrok for local testing, or your
   production host for the submitted demo).
2. `docker compose up` running with seeded clinic data:
   ```bash
   docker compose exec backend python -m scripts.seed_clinic
   ```
3. Retell account API key (webhook-capable key).
4. Set in `.env`:
   ```
   RETELL_API_KEY=key_xxx
   RETELL_VERIFY_SIGNATURES=true
   ```

Replace `{{BACKEND_BASE_URL}}` everywhere with your real base URL, e.g. `https://abcd.ngrok-free.app`.

## 2. Create the Retell LLM (single-prompt)

Dashboard → **LLM** → Create:

1. **Model:** GPT-4o (or Retell’s current recommended default with strong Hindi).
2. **General prompt:** paste the full contents of `docs/prompts/SYSTEM_PROMPT.md`.
3. **Begin message:**  
   `Namaste, thank you for calling Sunrise Multispecialty Clinic. This is Maya — how can I help you today?`
4. **Functions:** add each JSON file under `docs/retell/tools/` as a Custom Function:
   - URL: `https://YOUR_HOST/webhooks/retell/tools`
   - Method: `POST`
   - Parameters: copy the `parameters` object from each JSON file
   - Enable **Speak during execution** / typing sound as preferred
   - Timeout: 10–15s as listed
5. Do **not** enable “Payload: args only” for these tools — the adapter expects Retell’s default `{ name, args, call }` envelope.

## 3. Create the Retell Agent

Dashboard → **Agents** → Create / Edit:

| Setting | Value |
|---|---|
| LLM | The LLM created above |
| Voice | ElevenLabs multilingual voice that supports English + Hindi |
| Language | Multi / Auto (not English-only) |
| Interruption sensitivity | Medium–High |
| Responsiveness | High |
| Backchannel | On (optional) |
| Reminder message | Soft nudge after ~10s silence |
| Webhook | `https://YOUR_HOST/webhooks/retell/call-ended` |

### Why these speech settings

- **Interruption sensitivity Medium–High:** assignment requires natural barge-in without being hypersensitive to room noise.
- **Multilingual STT + ElevenLabs TTS:** satisfies English / Hindi / mid-call code-switching without a hardcoded dictionary.
- **Speak during execution on tools:** masks tool latency with a holding phrase from the prompt.

## 4. Phone number

1. Buy / assign a Retell number in the dashboard.
2. Bind it to this agent.
3. Place a test call from a phone whose number can be added as a seeded patient if needed.
4. Record the assigned number in the submission email or a private deployment note;
   do not commit it, the API key, or your public deployment URL.

## 5. Pre-submission deployment checklist

- [ ] The deployed service uses `ENV=production`, `RETELL_VERIFY_SIGNATURES=true`,
  and a real `RETELL_API_KEY` injected by the hosting platform.
- [ ] `GET /health/ready` succeeds over the public HTTPS URL.
- [ ] Every Retell Custom Function points to
  `https://YOUR_HOST/webhooks/retell/tools`, not a local or ngrok URL that has
  expired.
- [ ] The call-ended webhook points to
  `https://YOUR_HOST/webhooks/retell/call-ended`.
- [ ] A Retell phone number is bound to this agent.
- [ ] The local test suite and the manual
  [live test questions](../LIVE_TEST_QUESTIONS.md) have been run.
- [ ] The submission email or private write-up supplies the test phone number to
  reviewers; repository files remain secret-free.

## 6. Tool → backend mapping

| Retell tool | Backend behavior |
|---|---|
| `lookup_patient` | `PatientService` by phone and/or name |
| `get_clinic_catalog` | Live DB catalog (Retell-only helper; not a `/tools` route) |
| `list_appointments` | `AppointmentService.list_for_patient` — lets the agent find a real `appointment_id` for reschedule/cancel without the caller quoting one |
| `search_availability` | `AvailabilityService.search` (no cache) |
| `create_appointment` | `AppointmentService.create` + generated Idempotency-Key |
| `reschedule_appointment` | `AppointmentService.reschedule` |
| `cancel_appointment` | `AppointmentService.cancel` |
| `create_followup` | Upserts `Call` from Retell `call_id`, then `FollowUpService.create` |

## 7. Security

- Requests include `X-Retell-Signature`.
- When `RETELL_API_KEY` is set and `RETELL_VERIFY_SIGNATURES=true`, invalid signatures are rejected with 422.
- Production refuses to run the webhook without an API key.

## 8. Stack note (plan vs this milestone)

The long-term architecture plan includes a Custom LLM WebSocket orchestrator for deterministic slot state. This milestone ships the **Retell LLM + Custom Functions** path so the agent is dashboard-configurable and live-callable first. The tool adapter and `/tools` services are shared; a later milestone can move the brain behind Custom LLM without rewriting the scheduling backend.
