"""Prometheus scrape endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.metrics import prometheus_payload

router = APIRouter(tags=["prometheus"])


@router.get(
    "/metrics",
    summary="Prometheus-compatible metrics scrape endpoint",
    include_in_schema=True,
)
async def prometheus_metrics() -> Response:
    body, content_type = prometheus_payload()
    return Response(content=body, media_type=content_type)
