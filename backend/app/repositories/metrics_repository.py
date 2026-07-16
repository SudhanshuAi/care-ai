"""Aggregation queries over persisted metric events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.metric_event import MetricEvent


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _since_filter(self, statement: Select[Any], since: datetime | None) -> Select[Any]:
        if since is not None:
            return statement.where(MetricEvent.occurred_at >= since)
        return statement

    async def count(self, name: str, *, since: datetime | None = None) -> int:
        statement = select(func.count()).select_from(MetricEvent).where(
            MetricEvent.name == name
        )
        statement = self._since_filter(statement, since)
        return int(await self._session.scalar(statement) or 0)

    async def average_duration_ms(
        self, name: str, *, since: datetime | None = None
    ) -> float | None:
        statement = select(func.avg(MetricEvent.duration_ms)).where(
            MetricEvent.name == name,
            MetricEvent.duration_ms.is_not(None),
        )
        statement = self._since_filter(statement, since)
        value = await self._session.scalar(statement)
        return round(float(value), 2) if value is not None else None

    async def language_breakdown(
        self, *, since: datetime | None = None
    ) -> dict[str, int]:
        # Use a SQL literal for the JSON key so SELECT and GROUP BY share
        # the same expression under asyncpg's unique bind parameters.
        language_expr = func.coalesce(
            MetricEvent.labels.op("->>")(literal_column("'language'")),
            literal_column("'unknown'"),
        ).label("language")
        statement = (
            select(language_expr, func.count())
            .where(MetricEvent.name == "language")
            .group_by(language_expr)
        )
        statement = self._since_filter(statement, since)
        rows = (await self._session.execute(statement)).all()
        return {str(language): int(count) for language, count in rows}

    async def recent(
        self, *, limit: int = 50, since: datetime | None = None
    ) -> list[MetricEvent]:
        statement = select(MetricEvent).order_by(MetricEvent.occurred_at.desc()).limit(
            limit
        )
        statement = self._since_filter(statement, since)
        return list((await self._session.scalars(statement)).all())

    async def counts_by_name(
        self, *, since: datetime | None = None
    ) -> dict[str, int]:
        statement = select(MetricEvent.name, func.count()).group_by(MetricEvent.name)
        statement = self._since_filter(statement, since)
        rows = (await self._session.execute(statement)).all()
        return {str(name): int(count) for name, count in rows}
