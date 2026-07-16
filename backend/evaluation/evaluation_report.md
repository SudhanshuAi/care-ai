# Evaluation Report

## Summary

| Metric | Value |
|---|---:|
| total_cases | 18 |
| passed_cases | 18 |
| failed_cases | 0 |
| conversation_success_rate | 1.0 |
| booking_accuracy | 1.0 |
| tool_accuracy | 1.0 |
| average_tool_latency_ms | 23.05 |
| average_booking_latency_ms | 24.87 |
| average_response_latency_ms | 21.39 |
| average_retries | 0.06 |
| average_ttft_ms | not collected |

## Cases

| Case | Scenario | Result |
|---|---|---|
| shared_phone | shared_phone | PASS |
| single_patient | single_patient | PASS |
| earliest_slot | earliest_slot | PASS |
| exact_time_booking | exact_time_booking | PASS |
| cancel | cancel | PASS |
| reschedule | reschedule | PASS |
| hindi | language_lookup | PASS |
| english | language_lookup | PASS |
| code_switching | language_lookup | PASS |
| human_callback | followup | PASS |
| clinical_concern | followup | PASS |
| double_booking | double_booking | PASS |
| idempotency_replay | idempotency_replay | PASS |
| doctor_unavailable | doctor_unavailable | PASS |
| branch_unavailable | branch_unavailable | PASS |
| outside_schedule | outside_schedule | PASS |
| dropped_call | dropped_call | PASS |
| resume_conversation | resume_conversation | PASS |

## Failures

No failures.

## Metric Notes

- `average_ttft_ms`: not_collected: this harness does not invoke an LLM/TTS streaming runtime or provider call analytics.
- `average_response_latency_ms`: ASGI request round-trip time; this is backend response latency, not spoken end-to-end response latency.
- `average_retries`: Explicit replay attempts made by the harness per evaluated case.
