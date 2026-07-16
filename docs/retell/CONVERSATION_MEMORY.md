# Conversation Memory and Call Resume

## Storage

Conversation memory is persisted on the existing `calls` table; no
Redis, in-memory cache, or second conversation table is used. This makes
resume state survive application restarts and deploys.

Each Retell invocation creates or restores a `Call` row and stores:

- Retell `call_id` and database `resumed_from_call_id`
- `language` and `current_intent`
- identified patient plus selected branch, practitioner, and appointment type
- `last_availability_search` (arguments and live result)
- `pending_confirmation` (offered slots awaiting caller approval)
- `conversation_summary`, `last_tool_called`, and `last_updated_at`

## Resume behavior

`RetellToolDispatcher` calls `ConversationStateService.restore_or_create`
before every Retell tool dispatch.

1. If Retell sends `call.resumed_from_call_id`, the new call inherits
   the referenced call's resumable state.
2. If Retell does not provide that value, an inbound callback from the
   same phone number resumes the latest explicitly `disconnected` call
   for that phone. We intentionally do not auto-resume `in_progress`
   rows, because they may represent a concurrent or stale call.
3. Completed calls are deliberately not treated as interrupted work.
4. The original `/tools/*` API remains unchanged.

When a resumed caller asks to continue, the agent should use the
returned state instead of restarting discovery. In particular, it should
not re-ask known identity, branch, doctor, or date/time preferences.

## Operations endpoint

```text
GET /webhooks/retell/call-context/{retell_call_id}
```

Example:

```bash
curl http://localhost:8000/webhooks/retell/call-context/retell-resumed-123
```

The response contains the durable state and `restored: true` when the
call is linked to an earlier call.

## Call-end behavior

`POST /webhooks/retell/call-ended`:

- marks normal call ends as `completed`;
- marks payloads with disconnect/error/failed status as `disconnected`;
- generates a concise deterministic summary from the latest state;
- keeps disconnected context resumable.

## Retell prompt/dashboard addition

Add this instruction to the Retell system prompt:

> When you receive resumed call context, briefly acknowledge the
> interruption and continue from the saved intent and selections. Do not
> repeat questions already represented in call context. If the caller
> changes time, doctor, or branch, run a new live availability search.
