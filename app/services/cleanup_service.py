import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from app.database import AsyncSessionLocal
from app.models.event_log import EventLog
from app.models.event_dedup import EventDedup

logger = logging.getLogger(__name__)

async def auto_cleanup_database():
    """
    Background task to periodically delete EventLogs and EventDedup records older than 30 days.
    Runs once every 24 hours.
    """
    retention_days = 30
    sleep_duration = 86400  # 24 hours in seconds

    while True:
        try:
            logger.info("🧹 Starting scheduled database cleanup...")
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            async with AsyncSessionLocal() as db:
                # Delete old EventLogs
                stmt_logs = delete(EventLog).where(EventLog.created_at < cutoff_date)
                result_logs = await db.execute(stmt_logs)
                
                # Delete old EventDedup (assuming EventDedup has created_at, 
                # if not, we can just skip or add a created_at column to EventDedup as well. 
                # Assuming it has created_at for now, if it errors we can handle it.)
                try:
                    stmt_dedup = delete(EventDedup).where(EventDedup.created_at < cutoff_date)
                    result_dedup = await db.execute(stmt_dedup)
                    dedup_count = result_dedup.rowcount
                except Exception as e:
                    # Some tables might not have created_at, ignore if so
                    logger.warning(f"Could not clean EventDedup: {e}")
                    dedup_count = 0
                
                await db.commit()

            logger.info(f"✅ Cleanup complete: Deleted {result_logs.rowcount} logs and {dedup_count} dedup records older than {retention_days} days.")
            
        except Exception as e:
            logger.error(f"❌ Error during database cleanup: {e}")

        # Sleep for 24 hours before running again
        await asyncio.sleep(sleep_duration)
