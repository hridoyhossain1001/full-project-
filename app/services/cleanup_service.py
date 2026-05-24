import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from app.database import AsyncSessionLocal
from app.models.event_log import EventLog
from app.models.event_dedup import EventDedup
from app.models.event_outbox import EventOutbox
from app.models.failed_event import FailedEvent
from app.models.usage_counter import UsageCounter
from app.models.client_session import ClientSession

logger = logging.getLogger(__name__)

# Max rows to delete per batch — prevents long table locks
CLEANUP_BATCH_SIZE = 5000


async def _batched_delete(db, model, condition, batch_size: int = CLEANUP_BATCH_SIZE) -> int:
    """Delete rows matching `condition` in batches to avoid long table locks."""
    total_deleted = 0
    while True:
        # Find IDs to delete in this batch
        id_query = select(model.id).where(condition).limit(batch_size)
        result = await db.execute(id_query)
        ids = result.scalars().all()
        if not ids:
            break
        stmt = delete(model).where(model.id.in_(ids))
        del_result = await db.execute(stmt)
        total_deleted += del_result.rowcount
        await db.commit()
        # Yield to event loop between batches
        await asyncio.sleep(0.1)
    return total_deleted


async def auto_cleanup_database():
    """
    Background task to periodically delete old records.
    Cleans: EventLogs (30d), EventDedup (30d), EventOutbox sent/dead (30d),
    FailedEvents dead/success (30d), UsageCounters (400d).
    Uses batched deletes for large tables to prevent long table locks.
    Runs once every 24 hours.
    """
    retention_days = 30
    usage_retention_days = 400  # Keep monthly quota counters long enough for audits.
    sleep_duration = 86400  # 24 hours in seconds

    while True:
        try:
            logger.info("🧹 Starting scheduled database cleanup...")
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
            usage_cutoff = datetime.now(timezone.utc) - timedelta(days=usage_retention_days)

            async with AsyncSessionLocal() as db:
                # Delete old EventLogs (batched — can be millions of rows)
                logs_deleted = await _batched_delete(
                    db, EventLog, EventLog.created_at < cutoff_date
                )

                # Delete old EventDedup (batched)
                try:
                    dedup_deleted = await _batched_delete(
                        db, EventDedup, EventDedup.created_at < cutoff_date
                    )
                except Exception as e:
                    logger.warning(f"Could not clean EventDedup: {e}")
                    dedup_deleted = 0

                # Delete completed/dead FailedEvents (no longer needed for retry)
                try:
                    failed_deleted = await _batched_delete(
                        db,
                        FailedEvent,
                        (FailedEvent.status.in_(["success", "dead"]))
                        & (FailedEvent.created_at < cutoff_date),
                    )
                except Exception as e:
                    logger.warning(f"Could not clean FailedEvents: {e}")
                    failed_deleted = 0

                # Delete old outbox rows that are no longer actionable.
                try:
                    outbox_deleted = await _batched_delete(
                        db,
                        EventOutbox,
                        (EventOutbox.status.in_(["sent", "dead"]))
                        & (EventOutbox.created_at < cutoff_date),
                    )
                except Exception as e:
                    logger.warning(f"Could not clean EventOutbox: {e}")
                    outbox_deleted = 0

                # Delete old UsageCounters (rate + daily windows older than retention)
                try:
                    usage_deleted = await _batched_delete(
                        db,
                        UsageCounter,
                        UsageCounter.created_at < usage_cutoff,
                    )
                except Exception as e:
                    logger.warning(f"Could not clean UsageCounters: {e}")
                    usage_deleted = 0

                # Delete expired/revoked ClientSessions
                try:
                    sessions_deleted = await _batched_delete(
                        db,
                        ClientSession,
                        (ClientSession.expires_at < cutoff_date)
                        | (
                            (ClientSession.revoked_at.is_not(None))
                            & (ClientSession.created_at < cutoff_date)
                        ),
                    )
                except Exception as e:
                    logger.warning(f"Could not clean ClientSessions: {e}")
                    sessions_deleted = 0

            logger.info(
                f"✅ Cleanup complete: Deleted {logs_deleted} logs, "
                f"{dedup_deleted} dedup, {failed_deleted} failed events, "
                f"{outbox_deleted} outbox rows, {usage_deleted} usage counters, "
                f"{sessions_deleted} sessions "
                f"(retention: {retention_days}d logs, {usage_retention_days}d counters)."
            )

        except Exception as e:
            logger.error(f"❌ Error during database cleanup: {e}")

        # Sleep for 24 hours before running again
        await asyncio.sleep(sleep_duration)
