# Bolna Dashboard Configuration

Wires **Bolna Voice AI** to Care AI via a thin adapter:

`POST {{BACKEND_BASE_URL}}/webhooks/bolna/tools/{tool_name}`

`/tools/*` REST APIs stay unchanged. The Bolna adapter reuses the same
tool dispatcher as Retell.

## 1. Backend env (Render / `.env`)

```bash
BOLNA_API_TOKEN=bolna_shared_secret_change_me
BOLNA_VERIFY_AUTH=true
ENV=production
```

Use the same token in every Bolna tool's `api_token` field as
`Bearer bolna_shared_secret_change_me`.

Locally you can leave `BOLNA_API_TOKEN` blank and set
`BOLNA_VERIFY_AUTH=false`.

## 2. Agent prompt

Paste [../prompts/SYSTEM_PROMPT.md](../prompts/SYSTEM_PROMPT.md) into the
Bolna agent prompt. Add context lines so Bolna can auto-fill call metadata:

```text
Caller phone (from_number): {from_number}
Call id (call_sid): {call_sid}
Agent id: {agent_id}
```

## 3. Agent webhook

Set the agent **Webhook URL** to:

```text
https://YOUR_HOST/webhooks/bolna/call-status
```

Bolna will POST execution updates; the adapter marks our `calls` row
completed on terminal statuses.

## 4. Custom tools

In the Bolna **Tools** tab, add each JSON file under `tools/` via
**Write manually**. For every tool:

1. Keep `"key": "custom_task"` exactly.
2. Replace `{{BACKEND_BASE_URL}}` with your Render URL
   (e.g. `https://care-ai-backend-321k.onrender.com`).
3. Set `api_token` to `Bearer <same as BOLNA_API_TOKEN>`.
4. Prefer **per-tool URLs** ending in `/webhooks/bolna/tools/<name>`.

| Tool file | URL path |
|---|---|
| `lookup_patient.json` | `/webhooks/bolna/tools/lookup_patient` |
| `get_clinic_catalog.json` | `/webhooks/bolna/tools/get_clinic_catalog` |
| `search_availability.json` | `/webhooks/bolna/tools/search_availability` |
| `create_appointment.json` | `/webhooks/bolna/tools/create_appointment` |
| `reschedule_appointment.json` | `/webhooks/bolna/tools/reschedule_appointment` |
| `cancel_appointment.json` | `/webhooks/bolna/tools/cancel_appointment` |
| `create_followup.json` | `/webhooks/bolna/tools/create_followup` |

## 5. Call context fields

Include these optional parameters on tools that need caller identity
(already present in the JSON files). When the agent prompt exposes
`{from_number}` / `{call_sid}`, Bolna fills them without asking the caller:

- `from_number` — inbound caller ID
- `call_sid` — telephony / Bolna call id (stored as `bolna:<id>` in our DB)
- `execution_id` — fallback id if `call_sid` is missing

## 6. Smoke test

```bash
curl -X POST "https://YOUR_HOST/webhooks/bolna/tools/get_clinic_catalog" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer bolna_shared_secret_change_me" \
  -d '{"call_sid":"smoke-1","from_number":"+91-98765-10001"}'
```

Expect `{"ok":true,"tool":"get_clinic_catalog","result":{...}}`.

## Notes

- Bolna does **not** use Retell's `X-Retell-Signature`. Do not put a Bolna
  key into `RETELL_API_KEY`.
- You can run Retell and Bolna adapters side by side; they share services.
- `patient_id` must still be a UUID from `lookup_patient`, never
  `"new_patient"` or a name.
