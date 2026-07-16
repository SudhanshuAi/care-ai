"""Admin-facing metric aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.metrics_repository import MetricsRepository


class MetricsService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = MetricsRepository(session)

    @staticmethod
    def _window_start(hours: int | None) -> datetime | None:
        if hours is None or hours <= 0:
            return None
        return datetime.now(UTC) - timedelta(hours=hours)

    async def aggregated(self, *, hours: int | None = 24) -> dict[str, Any]:
        since = self._window_start(hours)
        counts = await self._repo.counts_by_name(since=since)
        return {
            "window_hours": hours,
            "since": since.isoformat() if since else None,
            "generated_at": datetime.now(UTC).isoformat(),
            "counts": counts,
            "call_duration_ms_avg": await self._repo.average_duration_ms(
                "call_duration", since=since
            ),
            "tool_latency_ms_avg": await self._repo.average_duration_ms(
                "tool_latency", since=since
            ),
            "endpoint_latency_ms_avg": await self._repo.average_duration_ms(
                "endpoint_latency", since=since
            ),
            "llm_latency_ms_avg": await self._repo.average_duration_ms(
                "llm_latency", since=since
            ),
            "booking_success": counts.get("booking_success", 0),
            "booking_failure": counts.get("booking_failure", 0),
            "cancel_success": counts.get("cancel_success", 0),
            "reschedule_success": counts.get("reschedule_success", 0),
            "interruptions": counts.get("interruption", 0),
            "tool_retries": counts.get("tool_retry", 0),
            "languages": await self._repo.language_breakdown(since=since),
        }

    async def dashboard(self, *, hours: int | None = 24) -> dict[str, Any]:
        summary = await self.aggregated(hours=hours)
        booking_attempts = (
            summary["booking_success"] + summary["booking_failure"]
        )
        summary["booking_success_rate"] = (
            round(summary["booking_success"] / booking_attempts, 4)
            if booking_attempts
            else None
        )
        recent = await self._repo.recent(limit=25, since=self._window_start(hours))
        summary["recent_events"] = [
            {
                "id": str(event.id),
                "name": event.name,
                "value": event.value,
                "duration_ms": event.duration_ms,
                "labels": event.labels,
                "call_id": event.call_id,
                "occurred_at": event.occurred_at.isoformat()
                if event.occurred_at
                else None,
            }
            for event in recent
        ]
        summary["notes"] = {
            "llm_latency": (
                "Collected when an orchestrator or CallTurn writer records "
                "llm_latency / llm_ttft_ms. Provider-hosted Retell LLM "
                "latency is not visible to this backend by default."
            )
        }
        return summary
