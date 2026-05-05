import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select, and_, func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.event import EventsPayload, EventsResponse
from app.dependencies import get_current_client
from app.services.capi_service import send_to_facebook
from app.models.client import Client
from app.models.event_log import EventLog
from app.database import get_db
from app.services.retry_service import save_failed_event

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post(
    "/events",
    response_model=EventsResponse,
    summary="Facebook CAPI Events Endpoint",
)
async def receive_events(
    request: Request,
    payload: EventsPayload,
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    ক্লায়েন্টের API Key ভেরিফাই করে Facebook CAPI-তে ইভেন্ট ফরওয়ার্ড করে।
    প্রতিটি কল event_logs টেবিলে সংরক্ষিত হয়।
    Deduplication: একই event_id আবার পাঠানো হলে skip করে।
    """
    if not payload.data:
        raise HTTPException(status_code=400, detail="ইভেন্ট ডাটা খালি!")

    client_ip = request.client.host if request.client else None

    # ─── Per-Client Rate Limit Check ─────────────────────────────────────
    rate_limit = client.rate_limit or 5000  # default 5000/min
    one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    recent_result = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(
                EventLog.client_id == client.id,
                EventLog.created_at >= one_min_ago,
            )
        )
    )
    recent_count = recent_result.scalar() or 0
    if recent_count + len(payload.data) > rate_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded! {recent_count}/{rate_limit} events/min"
        )

    # ─── Daily Quota Check: আজকে কতগুলো ইভেন্ট পাঠানো হয়েছে ──────────
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count_result = await db.execute(
        select(sql_func.coalesce(sql_func.sum(EventLog.event_count), 0)).where(
            and_(
                EventLog.client_id == client.id,
                EventLog.status == "success",
                EventLog.created_at >= today_start,
            )
        )
    )
    today_count = today_count_result.scalar() or 0

    if client.daily_quota and today_count + len(payload.data) > client.daily_quota:
        raise HTTPException(
            status_code=429,
            detail=f"Daily quota exceeded! আজকে {today_count}/{client.daily_quota} ইভেন্ট পাঠানো হয়েছে।"
        )

    # ─── Deduplication: event_id চেক করে duplicate বাদ দাও ─────────────
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    unique_events = []
    for event in payload.data:
        if event.event_id:
            # EventLog.event_id column-এ exact match (indexed, fast)
            existing = await db.execute(
                select(EventLog.id).where(
                    and_(
                        EventLog.client_id == client.id,
                        EventLog.event_id == event.event_id,
                        EventLog.status == "success",
                        EventLog.created_at >= cutoff,
                    )
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                logger.info(f"[{client.name}] Duplicate event skipped: {event.event_id}")
                continue
        unique_events.append(event)

    if not unique_events:
        return EventsResponse(
            status="success",
            events_received=0,
            message="সব ইভেন্ট আগেই পাঠানো হয়েছে (deduplicated)"
        )

    event_names = ", ".join(set(e.event_name for e in unique_events))

    try:
        # CAPI সার্ভিসে ডাটা পাঠানো
        result = await send_to_facebook(client, unique_events)

        # ✅ সফল হলে প্রতিটি event আলাদাভাবে লগ করো (dedup-এর জন্য event_id store)
        for ev in unique_events:
            log_entry = EventLog(
                client_id=client.id,
                event_name=ev.event_name,
                event_id=ev.event_id,
                event_count=1,
                status="success",
                fb_response=json.dumps(result) if result else None,
                ip_address=client_ip,
            )
            db.add(log_entry)
        await db.commit()

        return EventsResponse(
            status="success",
            events_received=len(unique_events),
            message="সফলভাবে Facebook-এ পাঠানো হয়েছে"
        )

    except Exception as e:
        # ❌ ব্যর্থ হলে error লগ + retry queue-তে সেভ করো
        error_msg = str(e)
        logger.error(f"Client {client.name} | Error: {error_msg}")

        try:
            log_entry = EventLog(
                client_id=client.id,
                event_name=event_names,
                event_count=len(unique_events),
                status="failed",
                error_message=error_msg[:500],
                ip_address=client_ip,
            )
            db.add(log_entry)
            await db.commit()

            # 🔄 Retry queue-তে সেভ করো
            events_as_dicts = [ev.model_dump(exclude_none=True) for ev in unique_events]
            await save_failed_event(db, client.id, events_as_dicts, error_msg)

        except Exception:
            logger.error("Failed to save error log to database")

        raise HTTPException(
            status_code=502,
            detail="Facebook API তে সমস্যা — ইভেন্ট retry queue-তে রাখা হয়েছে"
        )

