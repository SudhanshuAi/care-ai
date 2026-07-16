# Retell, Bolna, and Render production checklist

Use this checklist after deploying the commits that add deterministic
guardrails, structured observability, and the updated conversational prompt.
The provider dashboards do not automatically pull files from this repository:
copy the prompt manually, and keep the existing tool contracts unchanged.

## Deployment order

1. Deploy the backend to Render and wait for `GET /health/live` to return `200`.
2. Confirm Render startup completed `alembic upgrade head`. This deploy creates
   the availability-offer and observability-related schema expected by the new
   booking flow.
3. Update Retell and/or Bolna to use the deployed Render HTTPS URL.
4. Paste the current `docs/prompts/SYSTEM_PROMPT.md` into the active provider
   agent prompt.
5. Place an end-to-end test call for booking, rescheduling, cancellation, a
   callback request, Hindi, Hinglish, and a caller interruption.

## Render

Create or update a **Web Service** using the Docker deployment:

| Render setting | Value |
|---|---|
| Repository | This repository |
| Root directory / Docker build context | `backend` |
| Dockerfile path | `Dockerfile` |
| Health check path | `/health/live` |
| Public base URL | Record it as `https://YOUR-SERVICE.onrender.com` |

If Render exposes a **Docker Command** override, use:

```sh
sh -c 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

This ensures the server follows Render's assigned `PORT`. Do not use a
development command such as `uvicorn --reload`.

Configure these environment variables in Render. Use Render's secret-value
mechanism for every token and database URL; do not commit them to `.env`.

```dotenv
ENV=production
DEBUG=false
LOG_LEVEL=INFO
JSON_LOGS=true
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/DATABASE?ssl=require
DB_ECHO=false

RETELL_API_KEY=<Retell webhook-signing API key>
RETELL_AGENT_ID=<optional Retell agent id>
RETELL_LLM_ID=<optional Retell LLM id>
RETELL_VERIFY_SIGNATURES=true

BOLNA_API_TOKEN=<long random shared secret>
BOLNA_AGENT_ID=<optional Bolna agent id>
BOLNA_VERIFY_AUTH=true

# PMS (durable mock provider shipped with this backend)
PMS_PROVIDER=mock
PMS_RETRY_MAX_ATTEMPTS=5
PMS_RETRY_BASE_SECONDS=30
```

`DATABASE_URL` must use SQLAlchemy's `postgresql+asyncpg://` dialect. For a
hosted Postgres connection string beginning `postgres://` or `postgresql://`,
replace only the scheme with `postgresql+asyncpg://`; preserve the remaining
host, credentials, database name, and required SSL query options.

After the deploy:

- Check Render logs for the Alembic revision reaching `head`.
- Confirm `GET https://YOUR-HOST/health/live` returns `200`.
- Set up Render log streaming or an external drain for the JSON logs.
- Restrict access to `/admin/*`, `/metrics`, and call-context endpoints at the
  network/proxy layer if they are not intended to be public.
- Schedule `python -m scripts.retry_pms_syncs` as a Render cron job. It retries
  due `pending` and `pending_retry` mock-PMS write-backs with exponential
  backoff; confirmed appointments are never rolled back.

## Retell AI

### Required changes

1. In **LLM → General prompt**, replace the old prompt with the complete current
   contents of `docs/prompts/SYSTEM_PROMPT.md`.
2. Keep all seven existing Custom Functions. Do **not** change function names,
   URLs, parameter schemas, required fields, or the Retell default
   `{name, args, call}` payload format.
3. Replace `{{BACKEND_BASE_URL}}` in every function with the Render URL:

   ```text
   https://YOUR-SERVICE.onrender.com/webhooks/retell/tools
   ```

4. Set the agent call-lifecycle webhook to:

   ```text
   https://YOUR-SERVICE.onrender.com/webhooks/retell/call-ended
   ```

5. Keep a multilingual, Hindi-capable voice and STT in **Multi/Auto** language
   mode. Set interruption sensitivity to **Medium–High**, responsiveness to
   **High**, and enable at most one silence reminder.
6. Keep **Speak during execution** enabled if it is already in use, but do not
   configure static English-only execution speech. The new system prompt supplies
   short, language-matched holding phrases.
7. Ensure Retell sends `X-Retell-Signature`; production requests are rejected if
   signature verification is enabled without a valid `RETELL_API_KEY`.

### No Retell tool-definition change is needed

The backend now enforces fresh live availability before create/reschedule,
rejects invalid entities, and prevents duplicate follow-ups. Those checks occur
behind the existing endpoint. The new prompt tells the agent to search first
and obtain a natural explicit confirmation; it does not add a new function.

When debugging, capture the response headers on a tool invocation:

- `X-Request-ID` identifies one webhook request.
- `X-Call-ID` identifies the Retell call.
- `X-Conversation-ID` groups resumed/reconnected calls.

## Bolna AI

### Required changes

1. Replace the active agent prompt with the complete current
   `docs/prompts/SYSTEM_PROMPT.md`.
2. Preserve these prompt context variables so caller identity and call continuity
   remain available:

   ```text
   Caller phone (from_number): {from_number}
   Call id (call_sid): {call_sid}
   Agent id: {agent_id}
   ```

3. Set the agent lifecycle webhook to:

   ```text
   https://YOUR-SERVICE.onrender.com/webhooks/bolna/call-status
   ```

4. Keep the seven existing custom tools and their parameter definitions
   unchanged. For each, set its URL to:

   ```text
   https://YOUR-SERVICE.onrender.com/webhooks/bolna/tools/<tool_name>
   ```

5. Set each tool's Authorization/API token to:

   ```text
   Bearer <the exact BOLNA_API_TOKEN configured in Render>
   ```

6. Ensure Bolna sends `from_number` and `call_sid` with tool calls. `call_sid`
   is necessary to associate a follow-up and reconnect with the correct call.
7. Remove or avoid static English-only tool pre-call messages (for example,
   “Booking that for you now”). Let the agent use the prompt's language-matched
   holding phrase instead. Do not change the tool URL, parameters, or
   `custom_task` key.

Bolna tool responses include the same `X-Request-ID`, `X-Call-ID`, and
`X-Conversation-ID` correlation headers as Retell. Its structured tool logs
are labelled `provider=bolna`.

## Smoke-test acceptance criteria

For either provider, verify all of the following using a real test call:

- English, Hindi, and Hinglish replies follow the caller's language.
- The agent stops and listens when interrupted.
- A booking calls live availability before the final booking action.
- A booking/reschedule gets a short spoken confirmation and an explicit yes.
- Cancellation/reschedule fee wording appears only when the tool returned an
  applicable fee.
- A human request results in a callback promise, never an immediate transfer.
- Render logs contain `request_id`; Retell tool logs also contain call,
  conversation, tool, latency, status, language, and provider fields.

See `docs/ops/LOGGING.md` for field definitions and JSON-log examples.
