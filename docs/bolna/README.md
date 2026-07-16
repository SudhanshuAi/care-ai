# Bolna Integration

This adapter lets **Bolna Voice AI** call the same scheduling services as
Retell, without changing `/tools/*` REST contracts.

## Endpoints

| Bolna config | Backend |
|---|---|
| Each custom tool URL | `POST {{BACKEND_BASE_URL}}/webhooks/bolna/tools/{tool_name}` |
| Optional single URL | `POST {{BACKEND_BASE_URL}}/webhooks/bolna/tools` (body must include `tool` or `name`) |
| Agent `webhook_url` | `POST {{BACKEND_BASE_URL}}/webhooks/bolna/call-status` |

Auth: set `BOLNA_API_TOKEN` on Render and the same value as each tool's
`api_token` (`Bearer <token>`). Locally set `BOLNA_VERIFY_AUTH=false`.

## Quick local test

```bash
curl -X POST "http://localhost:8000/webhooks/bolna/tools/lookup_patient" \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Rahul Verma","from_number":"+91-98765-10001","call_sid":"test-1"}'
```

## Files

- [DASHBOARD_CONFIGURATION.md](DASHBOARD_CONFIGURATION.md) — Bolna agent setup
- [tools/](tools/) — pasteable Custom Function JSON for each tool
