"""Post-commit, idempotent synchronization to the configured PMS provider."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.metrics import record_event
from app.db.models.enums import PmsSyncStatus
from app.db.session import session_scope
from app.pms import MockPmsAdapter, PmsAdapter
from app.repositories.pms_repository import PmsRepository

logger = get_logger(__name__)
PmsAdapterFactory = Callable[[AsyncSession], PmsAdapter]


@dataclass(frozen=True)
class PmsSyncResult:
    appointment_id: UUID
    status: PmsSyncStatus
    attempted: bool
    detail: str | None = None


class PmsSyncService:
    """Synchronize committed appointments without affecting booking validity."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        adapter_factory: PmsAdapterFactory | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._adapter_factory = adapter_factory or self._build_adapter

    async def sync_appointment(
        self, appointment_id: UUID, *, operation: str = "create"
    ) -> PmsSyncResult:
        """Write one appointment lifecycle operation after its transaction commits."""

        async with session_scope() as session:
            repository = PmsRepository(session)
            appointment = await repository.appointment_for_sync(appointment_id)
            if appointment is None:
                return PmsSyncResult(
                    appointment_id=appointment_id,
                    status=PmsSyncStatus.FAILED,
                    attempted=False,
                    detail="Appointment no longer exists.",
                )
            if (
                appointment.pms_sync_status == PmsSyncStatus.SYNCED
                and appointment.pms_sync_operation == operation
            ):
                return PmsSyncResult(
                    appointment_id=appointment.id,
                    status=PmsSyncStatus.SYNCED,
                    attempted=False,
                )
            if appointment.pms_sync_operation != operation:
                appointment.pms_sync_operation = operation
                appointment.pms_sync_status = PmsSyncStatus.PENDING
                appointment.pms_sync_attempts = 0
                appointment.pms_last_attempt_at = None
                appointment.pms_synced_at = None
                appointment.pms_last_error = None
            if appointment.pms_sync_attempts >= self._settings.pms_retry_max_attempts:
                appointment.pms_sync_status = PmsSyncStatus.FAILED
                appointment.pms_last_error = (
                    "PMS retry limit reached before another write-back attempt."
                )
                result = PmsSyncResult(
                    appointment_id=appointment.id,
                    status=PmsSyncStatus.FAILED,
                    attempted=False,
                    detail=appointment.pms_last_error,
                )
            else:
                appointment.pms_sync_attempts += 1
                appointment.pms_last_attempt_at = datetime.now(UTC)
                try:
                    writeback = await self._adapter_factory(session).write_appointment(
                        appointment,
                        operation=operation,
                        idempotency_key=f"pms:{appointment.id}:{operation}",
                    )
                except Exception as exc:
                    detail = self._safe_error(exc)
                    appointment.pms_last_error = detail
                    appointment.pms_sync_status = (
                        PmsSyncStatus.FAILED
                        if appointment.pms_sync_attempts
                        >= self._settings.pms_retry_max_attempts
                        else PmsSyncStatus.PENDING_RETRY
                    )
                    result = PmsSyncResult(
                        appointment_id=appointment.id,
                        status=appointment.pms_sync_status,
                        attempted=True,
                        detail=detail,
                    )
                    logger.warning(
                        "pms_sync_failed",
                        appointment_id=str(appointment.id),
                        provider=self._settings.pms_provider,
                        operation=operation,
                        status=appointment.pms_sync_status.value,
                        attempts=appointment.pms_sync_attempts,
                        exception_type=type(exc).__name__,
                        detail=detail,
                    )
                else:
                    appointment.pms_sync_status = PmsSyncStatus.SYNCED
                    appointment.pms_synced_at = datetime.now(UTC)
                    appointment.pms_last_error = None
                    result = PmsSyncResult(
                        appointment_id=appointment.id,
                        status=PmsSyncStatus.SYNCED,
                        attempted=True,
                    )
                    logger.info(
                        "pms_sync_succeeded",
                        appointment_id=str(appointment.id),
                        provider=writeback.provider,
                        operation=operation,
                        external_reference=writeback.external_reference,
                        replayed=writeback.replayed,
                        attempts=appointment.pms_sync_attempts,
                        status=PmsSyncStatus.SYNCED.value,
                    )

        await record_event(
            name="pms_sync",
            value=1.0,
            labels={
                "provider": self._settings.pms_provider,
                "operation": operation,
                "status": result.status.value,
                "attempted": result.attempted,
            },
            detail=result.detail,
        )
        return result

    async def retry_pending(self, *, limit: int = 100) -> list[PmsSyncResult]:
        """Reconcile due pending write-backs, honoring exponential backoff."""

        async with session_scope() as session:
            candidates = await PmsRepository(session).retry_candidates(limit=limit)
            pending_operations = [
                (appointment.id, appointment.pms_sync_operation or "create")
                for appointment in candidates
                if self._retry_is_due(
                    attempts=appointment.pms_sync_attempts,
                    last_attempt_at=appointment.pms_last_attempt_at,
                )
            ]
        return [
            await self.sync_appointment(appointment_id, operation=operation)
            for appointment_id, operation in pending_operations
        ]

    def _build_adapter(self, session: AsyncSession) -> PmsAdapter:
        if self._settings.pms_provider.casefold() == "mock":
            return MockPmsAdapter(session)
        raise ValueError(
            f"Unsupported PMS_PROVIDER {self._settings.pms_provider!r}; "
            "only 'mock' is implemented."
        )

    def _retry_is_due(
        self, *, attempts: int, last_attempt_at: datetime | None
    ) -> bool:
        if last_attempt_at is None:
            return True
        if attempts >= self._settings.pms_retry_max_attempts:
            return True
        delay_seconds = self._settings.pms_retry_base_seconds * (2 ** max(attempts - 1, 0))
        return datetime.now(UTC) >= last_attempt_at + timedelta(seconds=delay_seconds)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        detail = str(exc).strip() or type(exc).__name__
        return detail[:500]
