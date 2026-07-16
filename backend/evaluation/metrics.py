"""Result models and aggregate metrics for the backend evaluation harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import fmean
from typing import Any


@dataclass(slots=True)
class StepResult:
    name: str
    success: bool
    latency_ms: float
    status_code: int | None = None
    tool: str | None = None
    booking_operation: bool = False
    retry: bool = False
    detail: str | None = None


@dataclass(slots=True)
class CaseResult:
    case_id: str
    scenario: str
    success: bool
    steps: list[StepResult] = field(default_factory=list)
    failure: str | None = None


def _average(values: list[float]) -> float | None:
    return round(fmean(values), 2) if values else None


def build_report(results: list[CaseResult]) -> dict[str, Any]:
    """Build a JSON-safe report without pretending HTTP time is voice TTFT."""

    steps = [step for result in results for step in result.steps]
    tool_steps = [step for step in steps if step.tool]
    booking_steps = [step for step in steps if step.booking_operation]
    passed_cases = [result for result in results if result.success]
    failures = [
        {
            "case_id": result.case_id,
            "scenario": result.scenario,
            "failure": result.failure or "One or more assertions failed.",
        }
        for result in results
        if not result.success
    ]

    return {
        "summary": {
            "total_cases": len(results),
            "passed_cases": len(passed_cases),
            "failed_cases": len(failures),
            "conversation_success_rate": (
                round(len(passed_cases) / len(results), 4) if results else None
            ),
            "booking_accuracy": (
                round(
                    sum(step.success for step in booking_steps) / len(booking_steps),
                    4,
                )
                if booking_steps
                else None
            ),
            "tool_accuracy": (
                round(sum(step.success for step in tool_steps) / len(tool_steps), 4)
                if tool_steps
                else None
            ),
            "average_tool_latency_ms": _average(
                [step.latency_ms for step in tool_steps]
            ),
            "average_booking_latency_ms": _average(
                [step.latency_ms for step in booking_steps]
            ),
            "average_response_latency_ms": _average(
                [step.latency_ms for step in steps]
            ),
            "average_retries": (
                round(sum(step.retry for step in steps) / len(results), 2)
                if results
                else None
            ),
            "average_ttft_ms": None,
        },
        "metric_notes": {
            "average_ttft_ms": (
                "not_collected: this harness does not invoke an LLM/TTS streaming "
                "runtime or provider call analytics."
            ),
            "average_response_latency_ms": (
                "ASGI request round-trip time; this is backend response latency, "
                "not spoken end-to-end response latency."
            ),
            "average_retries": (
                "Explicit replay attempts made by the harness per evaluated case."
            ),
        },
        "failures": failures,
        "cases": [
            {
                "case_id": result.case_id,
                "scenario": result.scenario,
                "success": result.success,
                "failure": result.failure,
                "steps": [asdict(step) for step in result.steps],
            }
            for result in results
        ],
    }
