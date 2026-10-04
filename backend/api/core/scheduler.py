"""
Periodic background cleanup scheduler.
Uses asyncio tasks — no external scheduler dependency needed.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


async def _cleanup_old_conversations(db_factory, max_age_days: int = 90) -> None:
    """Delete conversations older than max_age_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    async with db_factory() as db:
        from sqlalchemy import delete
        from api.models.conversation import Conversation
        result = await db.execute(delete(Conversation).where(Conversation.created_at < cutoff))
        await db.commit()
        if result.rowcount:
            logger.info("[scheduler] Purged %d old conversations", result.rowcount)


async def _cleanup_expired_audit_logs(db_factory, max_age_days: int = 365) -> None:
    """Purge audit logs older than 1 year (GDPR compliance)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    async with db_factory() as db:
        from sqlalchemy import delete
        from api.models.audit import AuditLog
        result = await db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
        await db.commit()
        if result.rowcount:
            logger.info("[scheduler] Purged %d old audit logs", result.rowcount)


async def _log_system_health() -> None:
    """Log periodic system health snapshot."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        logger.info(
            "[scheduler] health_snapshot",
            extra={"cpu_pct": cpu, "mem_pct": mem.percent, "mem_available_mb": mem.available // 1024 // 1024}
        )
    except ImportError:
        pass  # psutil optional


async def _retry_pilot_notifications(db_factory) -> None:
    """Retry durable Pilot notifications without coupling startup to email code."""
    from api.services.pilot_notification_service import retry_pending_pilot_notifications

    await retry_pending_pilot_notifications(db_factory)


async def _run_periodic(coro_factory, interval_seconds: int, name: str) -> None:
    """Run a coroutine factory on a schedule, handling errors gracefully."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await coro_factory()
        except asyncio.CancelledError:
            logger.info("[scheduler] %s cancelled, stopping", name)
            return
        except Exception as exc:
            logger.error("[scheduler] %s failed: %s", name, exc)


def start_scheduler(db_factory) -> list[asyncio.Task]:
    """Start all background cleanup tasks. Returns tasks for cancellation on shutdown."""
    tasks = [
        asyncio.create_task(
            _run_periodic(lambda: _cleanup_old_conversations(db_factory), 3600 * 24, "cleanup_conversations"),
            name="cleanup_conversations"
        ),
        asyncio.create_task(
            _run_periodic(lambda: _cleanup_expired_audit_logs(db_factory), 3600 * 24 * 7, "cleanup_audit_logs"),
            name="cleanup_audit_logs"
        ),
        asyncio.create_task(
            _run_periodic(_log_system_health, 300, "health_snapshot"),
            name="health_snapshot"
        ),
        asyncio.create_task(
            _run_periodic(
                lambda: _retry_pilot_notifications(db_factory),
                300,
                "pilot_notification_retry",
            ),
            name="pilot_notification_retry",
        ),
    ]
    logger.info("[scheduler] Started %d background tasks", len(tasks))
    return tasks
