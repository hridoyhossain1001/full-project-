import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from app.database import AsyncSessionLocal
from app.models.event_log import EventLog
from app.models.event_dedup import EventDedup
from app.models.event_outbox import EventOutbox
from app.models.failed_event import FailedEvent
from app.models.usage_counter import UsageCounter

logger = logging.getLogger(__name__)

async def auto_cleanup_database():
    """
    Background task to periodically delete old records.
    Cleans: EventLogs (30d), EventDedup (30d), EventOutbox sent/dead (30d),
    FailedEvents dead/success (30d), UsageCounters (400d).
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
                # Delete old EventLogs
                stmt_logs = delete(EventLog).where(EventLog.created_at < cutoff_date)
                result_logs = await db.execute(stmt_logs)
                logs_deleted = result_logs.rowcount
                
                # Delete old EventDedup
                try:
                    stmt_dedup = delete(EventDedup).where(EventDedup.created_at < cutoff_date)
                    result_dedup = await db.execute(stmt_dedup)
                    dedup_deleted = result_dedup.rowcount
                except Exception as e:
                    logger.warning(f"Could not clean EventDedup: {e}")
                    dedup_deleted = 0

                # Delete completed/dead FailedEvents (no longer needed for retry)
                try:
                    stmt_failed = delete(FailedEvent).where(
                        FailedEvent.status.in_(["success", "dead"]),
                        FailedEvent.created_at < cutoff_date,
                    )
                    result_failed = await db.execute(stmt_failed)
                    failed_deleted = result_failed.rowcount
                except Exception as e:
                    logger.warning(f"Could not clean FailedEvents: {e}")
                    failed_deleted = 0

                # Delete old outbox rows that are no longer actionable.
                try:
                    stmt_outbox = delete(EventOutbox).where(
                        EventOutbox.status.in_(["sent", "dead"]),
                        EventOutbox.created_at < cutoff_date,
                    )
                    result_outbox = await db.execute(stmt_outbox)
                    outbox_deleted = result_outbox.rowcount
                except Exception as e:
                    logger.warning(f"Could not clean EventOutbox: {e}")
                    outbox_deleted = 0

                # Delete old UsageCounters (rate + daily windows older than 7 days)
                try:
                    stmt_usage = delete(UsageCounter).where(
                        UsageCounter.created_at < usage_cutoff,
                    )
                    result_usage = await db.execute(stmt_usage)
                    usage_deleted = result_usage.rowcount
                except Exception as e:
                    logger.warning(f"Could not clean UsageCounters: {e}")
                    usage_deleted = 0
                
                await db.commit()

            logger.info(
                f"✅ Cleanup complete: Deleted {logs_deleted} logs, "
                f"{dedup_deleted} dedup, {failed_deleted} failed events, "
                f"{outbox_deleted} outbox rows, {usage_deleted} usage counters "
                f"(retention: {retention_days}d logs, {usage_retention_days}d counters)."
            )
            
        except Exception as e:
            logger.error(f"❌ Error during database cleanup: {e}")

        # Sleep for 24 hours before running again
        await asyncio.sleep(sleep_duration)
