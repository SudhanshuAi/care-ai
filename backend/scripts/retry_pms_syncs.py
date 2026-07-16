"""Retry durable PMS write-backs after transient failures.

Run this as a Render cron job or one-shot worker:

    python -m scripts.retry_pms_syncs
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.pms_sync_service import PmsSyncService

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)
    results = await PmsSyncService(settings=settings).retry_pending()
    logger.info(
        "pms_reconciliation_complete",
        attempted=len(results),
        synced=sum(result.status.value == "synced" for result in results),
        failed=sum(result.status.value == "failed" for result in results),
        pending_retry=sum(result.status.value == "pending_retry" for result in results),
    )


if __name__ == "__main__":
    asyncio.run(main())
