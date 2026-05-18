"""
Durable event outbox worker.

The /events endpoint persists accepted events into event_outbox and returns quickly.
This worker claims queued rows and sends them to downstream services.
"""
import asyncio
import json
import logging
import os
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from app.database import AsyncSessionLocal
from app.dependencies import _snapshot
from app.models.client import Client
from app.models.event_log import EventLog
from app.models.event_outbox import EventOutbox
from app.schemas.event import EventData
from app.services.capi_service import send_to_facebook
from app.services.ga4_service import send_to_ga4
from app.services.tiktok_service import send_to_tiktok
from app.services.usage_service import rollback_usage_reservation
from app.services.webhook_service import send_webhook

logger = logging.getLogger(__name__)

WORKER_ID = os.getenv("EVENT_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
WORKER_BATCH_SIZE = int(os.getenv("EVENT_WORKER_BATCH_SIZE", "5"))
WORKER_POLL_SECONDS = float(os.getenv("EVENT_WORKER_POLL_SECONDS", "3.0"))
WORKER_STALE_LOCK_SECONDS = int(os.getenv("EVENT_WORKER_STALE_LOCK_SECONDS", "600"))
OUTBOX_MAX_ATTEMPTS = int(os.getenv("EVENT_OUTBOX_MAX_ATTEMPTS", "8"))
RETRY_DELAYS = [30, 120, 600, 1800, 3600, 7200, 14400, 28800]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_attempt_after(attempts: int) -> datetime:
    delay = RETRY_DELAYS[min(max(attempts - 1, 0), len(RETRY_DELAYS) - 1)]
    return _now() + timedelta(seconds=delay)


def _event_names(events: list[EventData]) -> str:
    return ", ".join(sorted({event.event_name for event in events}))


async def _log_secondary_failure(
    db,
    client_id: int,
    channel: str,
    event_names: str,
    event_count: int,
    error_message: str,
    ip_address: str | None,
) -> None:
    try:
        db.add(EventLog(
            client_id=client_id,
            event_name=f"{channel}:{event_names}"[:255],
            event_count=event_count,
            status="failed",
            error_message=str(error_message)[:500],
            ip_address=ip_address,
        ))
        await db.commit()
    except Exception as log_error:
        await db.rollback()
        logger.warning(f"Secondary failure logging failed: {log_error}")


async def enqueue_events(
    db,
    client_id: int,
    events_data: list[dict],
    request_context: dict,
    usage_reserved: dict[str, int],
) -> EventOutbox:
    outbox = EventOutbox(
        client_id=client_id,
        event_payload=events_data,
        request_context=request_context,
        usage_reserved=usage_reserved,
        status="queued",
        max_attempts=OUTBOX_MAX_ATTEMPTS,
        next_attempt_at=_now(),
    )
    db.add(outbox)
    await db.flush()
    return outbox


async def claim_due_events(db, limit: int = WORKER_BATCH_SIZE) -> list[EventOutbox]:
    now = _now()
    stale_before = now - timedelta(seconds=WORKER_STALE_LOCK_SECONDS)
    result = await db.execute(
        select(EventOutbox)
        .where(
            and_(
                EventOutbox.status.in_(["queued", "processing"]),
                EventOutbox.attempts < EventOutbox.max_attempts,
                EventOutbox.next_attempt_at <= now,
                or_(
                    EventOutbox.status == "queued",
                    EventOutbox.locked_at.is_(None),
                    EventOutbox.locked_at <= stale_before,
                ),
            )
        )
        .order_by(EventOutbox.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = result.scalars().all()
    for row in rows:
        row.status = "processing"
        row.locked_at = now
        row.locked_by = WORKER_ID
    if rows:
        await db.commit()
    else:
        await db.rollback()
    return rows


async def _mark_dead(db, row: EventOutbox, client, error_message: str) -> None:
    row.status = "dead"
    row.last_error = error_message[:500]
    row.locked_at = None
    row.locked_by = None
    if row.usage_reserved:
        try:
            await rollback_usage_reservation(db, client, row.usage_reserved)
        except Exception as usage_error:
            logger.warning(f"[{client.name}] Outbox usage rollback failed: {usage_error}")
    await db.commit()


async def process_outbox_row(row_id: int) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(EventOutbox, row_id)
        if not row or row.status != "processing":
            return

        client_result = await db.execute(select(Client).where(Client.id == row.client_id))
        client_row = client_result.scalar_one_or_none()
        if not client_row or not client_row.is_active:
            fallback_client = client_row or type("InactiveClient", (), {"id": row.client_id, "name": f"Client {row.client_id}"})()
            await _mark_dead(db, row, fallback_client, "Client inactive or missing")
            return

        client = _snapshot(client_row)
        events = [EventData(**event) for event in row.event_payload]
        context = row.request_context or {}
        event_names = _event_names(events)

        try:
            result = await send_to_facebook(client, events)

            row.status = "sent"
            row.sent_at = _now()
            row.locked_at = None
            row.locked_by = None
            row.last_error = None

            events_data = [event.model_dump(exclude_none=True) for event in events]
            for event_data in events_data:
                db.add(EventLog(
                    client_id=client.id,
                    event_name=event_data.get("event_name") or "unknown",
                    event_id=event_data.get("event_id"),
                    event_count=1,
                    status="success",
                    fb_response=json.dumps(result) if result else None,
                    ip_address=context.get("ip_address"),
                ))
            await db.commit()

            if client.tiktok_pixel_id and client.tiktok_access_token:
                try:
                    tiktok_result = await send_to_tiktok(client, events)
                    if not tiktok_result or tiktok_result.get("code") not in (0, None):
                        await _log_secondary_failure(
                            db,
                            client.id,
                            "TikTok",
                            event_names,
                            len(events),
                            tiktok_result or "TikTok send failed",
                            context.get("ip_address"),
                        )
                except Exception as secondary_error:
                    logger.warning(f"[{client.name}] TikTok secondary send failed: {secondary_error}")
                    await _log_secondary_failure(
                        db,
                        client.id,
                        "TikTok",
                        event_names,
                        len(events),
                        str(secondary_error),
                        context.get("ip_address"),
                    )

            if client.ga4_measurement_id and client.ga4_api_secret:
                try:
                    ga4_result = await send_to_ga4(
                        events=events_data,
                        measurement_id=client.ga4_measurement_id,
                        api_secret=client.ga4_api_secret,
                        cookies=context.get("cookies") or {},
                        ip_address=context.get("ip_address"),
                        user_agent=context.get("user_agent") or "",
                    )
                    if ga4_result and not ga4_result.get("ok", True):
                        await _log_secondary_failure(
                            db,
                            client.id,
                            "GA4",
                            event_names,
                            len(events),
                            ga4_result.get("error") or ga4_result,
                            context.get("ip_address"),
                        )
                except Exception as secondary_error:
                    logger.warning(f"[{client.name}] GA4 secondary send failed: {secondary_error}")
                    await _log_secondary_failure(
                        db,
                        client.id,
                        "GA4",
                        event_names,
                        len(events),
                        str(secondary_error),
                        context.get("ip_address"),
                    )

            if client.webhook_url:
                for event_data in events_data:
                    try:
                        await send_webhook(
                            client.webhook_url,
                            "event.sent",
                            {
                                "client_name": client.name,
                                "event_name": event_data.get("event_name"),
                                "event_id": event_data.get("event_id"),
                                "custom_data": event_data.get("custom_data", {}),
                            },
                        )
                    except Exception as secondary_error:
                        logger.warning(f"[{client.name}] Outbound webhook failed: {secondary_error}")
                        await _log_secondary_failure(
                            db,
                            client.id,
                            "Webhook",
                            event_data.get("event_name") or "unknown",
                            1,
                            str(secondary_error),
                            context.get("ip_address"),
                        )

            logger.info(f"[{client.name}] Outbox row {row.id} sent ({len(events)} events).")

        except Exception as exc:
            attempts = row.attempts + 1
            row.attempts = attempts
            row.last_error = str(exc)[:500]
            row.locked_at = None
            row.locked_by = None

            if attempts >= row.max_attempts:
                db.add(EventLog(
                    client_id=client.id,
                    event_name=event_names,
                    event_count=len(events),
                    status="failed",
                    error_message=row.last_error,
                    ip_address=context.get("ip_address"),
                ))
                await _mark_dead(db, row, client, row.last_error or "Outbox send failed")
                logger.error(f"[{client.name}] Outbox row {row.id} dead after {attempts} attempts.")
                return

            row.status = "queued"
            row.next_attempt_at = _next_attempt_after(attempts)
            await db.commit()
            logger.warning(
                f"[{client.name}] Outbox row {row.id} attempt {attempts} failed; "
                f"next retry at {row.next_attempt_at}: {str(exc)[:120]}"
            )


async def process_event_outbox_forever() -> None:
    logger.info(f"Event outbox worker started: {WORKER_ID}")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                rows = await claim_due_events(db)
            if rows:
                await asyncio.gather(*(process_outbox_row(row.id) for row in rows))
            else:
                await asyncio.sleep(WORKER_POLL_SECONDS)
        except Exception as exc:
            logger.error(f"Event outbox worker error: {exc}")
            await asyncio.sleep(WORKER_POLL_SECONDS)


if __name__ == "__main__":
    from app.services.cleanup_service import auto_cleanup_database
    from app.services.expiry_service import expire_old_pending_events
    from app.services.retry_service import retry_failed_events

    async def main() -> None:
        await asyncio.gather(
            process_event_outbox_forever(),
            retry_failed_events(),
            auto_cleanup_database(),
            expire_old_pending_events(),
        )

    asyncio.run(main())
