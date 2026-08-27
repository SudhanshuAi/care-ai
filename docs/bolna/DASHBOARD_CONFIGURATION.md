# Bolna Dashboard Configuration — Apollo Appointment Prototype

This configuration turns the Care AI backend into a Bolna-native appointment
assistant prototype. The demo uses synthetic patient, practitioner,
availability, and PMS data; it is not an authorized Apollo production
integration.

## 0. Rotate exposed credentials first

If a bearer token has appeared in a screenshot, chat, recording, document, or
commit, revoke it. Create a new random token, set it as `BOLNA_API_TOKEN` on
the backend, and put the same value in Bolna as `Bearer <token>`.

Never store the real value in this repository.

## 1. Backend environment

```text
BOLNA_API_TOKEN=<new-random-secret>
BOLNA_VERIFY_AUTH=true
ENV=production
```

The production backend must reject Bolna requests without the matching bearer
token.

## 2. Agent tab

| Setting | Recommended value |
|---|---|
| Agent name | `Maya – Apollo Appointment Assistant (Prototype)` |
| Welcome delay | `0 ms` |
| Ignore speech before welcome | On |
| Timezone | `Asia/Kolkata` |

**Welcome message**

```text
Namaste. You’ve reached the Apollo Clinics appointment assistant demo. Main Maya bol rahi hoon. How may I help?
```

**Hand-in / final message**

```text
Thank you for trying the Apollo Clinics appointment assistant demo. Take care.
```

Paste [APOLLO_SYSTEM_PROMPT.md](APOLLO_SYSTEM_PROMPT.md) into the agent prompt.
Do not paste the Retell prompt or the project README.

The prompt must retain these runtime context lines because Bolna uses them to
auto-inject call metadata into custom tools:

```text
Caller phone: {from_number}
Call ID: {call_sid}
Agent ID: {agent_id}
```

## 3. LLM

The existing Azure `gpt-4.1-mini` cluster is a reasonable low-latency starting
point.

| Setting | Starting value |
|---|---|
| Maximum generated tokens | `120–160` |
| Temperature | `0.2` |

The prompt deliberately limits spoken turns, so a large generation budget is
unnecessary. Increase it only if tool-call arguments are being truncated.

Leave Knowledge Base empty for the appointment demo. Patient identity,
catalog, availability, and mutation outcomes must come from tools, not
retrieved documents.

## 4. Languages, STT, and TTS

- Languages: Hindi primary plus English.
- STT: Deepgram `nova-3`.
- TTS: ElevenLabs Turbo v2.5 is a suitable low-latency starting point.
- Choose a natural multilingual Indian voice that matches Maya after previewing
  both Hindi and English. Avoid a voice that changes persona across languages.

Replace generic STT keywords such as “account number” and “customer service”
with the clinic vocabulary actually used by the demo:

```text
Apollo Clinics, Maya, Indiranagar, Koramangala, dermatology, dermatologist,
pediatrics, pediatrician, physiotherapy, dentist, dental checkup,
Ananya Rao, Karthik Iyer, Meera Nair, Sanjay Gupta, Priya Sharma
```

Keep these synchronized with the live catalog. The practitioner and patient
records in this prototype are synthetic.

## 5. Latency and interruptions

The current values are good starting points and match Bolna's documented
range:

| Setting | Value |
|---|---|
| Endpointing | `300 ms` |
| Linear delay | `500 ms` |
| Interruption threshold | `2 words` |
| User-online prompt | After `10 seconds` |

Configure both language variants for user-online detection:

- English: `Are you still on the line?`
- Hindi: `Kya aap abhi line par hain?`

Fifteen seconds of total user silence is aggressive for healthcare calls.
Start with `30–45 seconds`, then tune from recordings. Set total call timeout
to at least `300 seconds` for multi-step rescheduling flows.

Disable office ambience for evaluation calls. It makes ASR comparisons less
repeatable. Start noise cancellation around `70–80%` and adjust using real
Hindi/Hinglish recordings; excessive suppression can clip soft speech.

## 6. Custom tools — eight required

The agent must have all eight custom tools. Seven is not enough because
rescheduling and cancellation require `list_appointments` to obtain a real
appointment UUID.

| Tool | File |
|---|---|
| `lookup_patient` | [tools/lookup_patient.json](tools/lookup_patient.json) |
| `get_clinic_catalog` | [tools/get_clinic_catalog.json](tools/get_clinic_catalog.json) |
| `list_appointments` | [tools/list_appointments.json](tools/list_appointments.json) |
| `search_availability` | [tools/search_availability.json](tools/search_availability.json) |
| `create_appointment` | [tools/create_appointment.json](tools/create_appointment.json) |
| `reschedule_appointment` | [tools/reschedule_appointment.json](tools/reschedule_appointment.json) |
| `cancel_appointment` | [tools/cancel_appointment.json](tools/cancel_appointment.json) |
| `create_followup` | [tools/create_followup.json](tools/create_followup.json) |

For every file:

1. Keep `"key": "custom_task"`.
2. Replace `{{BACKEND_BASE_URL}}` with the deployed HTTPS backend URL.
3. Replace the token placeholder in Bolna with `Bearer <new token>`.
4. Keep the per-tool URL ending in `/webhooks/bolna/tools/<tool_name>`.
5. Do not wrap the URL in Markdown link syntax.

The neutral `One moment.` pre-call messages are intentional. Bolna speaks this
message automatically. The LLM prompt instructs Maya not to generate a second
holding phrase.

Do not add Bolna's generic Calendar Availability or Book Appointment tools;
they bypass the backend's patient checks, availability-offer guard, database
constraints, and mock-PMS lifecycle.

Do not add Transfer Call unless a real staffed destination and operating-hours
policy exist. This prototype uses `create_followup` and promises a callback.

## 7. Webhook configuration

Set the webhook URL to:

```text
https://YOUR_HOST/webhooks/bolna/call-status
```

Add this header using the newly rotated token:

```text
Authorization: Bearer <new token>
```

Triggering on all statuses is safe. The backend ignores non-terminal updates,
marks `completed` and other terminal outcomes complete, and marks
`call-disconnected` as disconnected so its durable state remains resumable.

## 8. Analytics and extractions

Keep Call Summary enabled. Useful structured extractions are:

- `intent`: book, reschedule, cancel, callback, unsupported
- `language`: English, Hindi, Hinglish, mixed
- `patient_resolution`: unique, ambiguous, not_found, not_attempted
- `outcome`: completed, unavailable, failed, followup_created, abandoned
- `appointment_id`: only when returned by a successful tool
- `followup_category`: human_requested, clinical_concern, other, none
- `tool_failure`: concise category, never raw secrets or request bodies

Do not extract or duplicate unnecessary medical information.

## 9. Smoke test

```bash
curl -X POST "https://YOUR_HOST/webhooks/bolna/tools/get_clinic_catalog" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <new token>" \
  -d '{"call_sid":"smoke-1","from_number":"+91-98765-10001"}'
```

Expect `{"ok":true,"tool":"get_clinic_catalog","result":{...}}`.

## 10. Required Bolna Chat tests

Test complete conversations, not isolated tools:

1. English booking with an underspecified time.
2. Hindi booking and mid-call switch to English.
3. Shared-phone disambiguation for Arjun and Kavya Mehta.
4. Earliest available slot without a date.
5. Changed branch or doctor after slots were offered.
6. Unavailable time followed by an alternative search.
7. Reschedule using `lookup_patient` → `list_appointments` → fresh search.
8. Cancellation using a real appointment ID.
9. Explicit request for a human callback.
10. Non-emergency clinical concern.
11. Potential emergency safety response.
12. Unmatched patient—no anonymous booking.
13. Caller interruption during a spoken response.
14. Tool error—no false confirmation.
