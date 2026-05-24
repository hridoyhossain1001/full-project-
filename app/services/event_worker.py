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
from app.services.delivery_service import deliver_events_to_platforms
from app.services.usage_service import rollback_usage_reservation
from app.utils.event_log_helpers import build_event_log_kwargs as _event_log_kwargs

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




# Secondary logging and delivery methods relocated to delivery_service.py


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
    """Mark an outbox row dead without committing the caller's transaction."""
    row.status = "dead"
    row.last_error = error_message[:500]
    row.locked_at = None
    row.locked_by = None
    if row.usage_reserved:
        try:
            async with db.begin_nested():
                await rollback_usage_reservation(db, client, row.usage_reserved)
        except Exception as usage_error:
            logger.warning(f"[{client.name}] Outbox usage rollback failed: {usage_error}")


async def process_outbox_row(row_id: int) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(EventOutbox, row_id)
        if not row or row.status != "processing":
            return

        client_result = await db.execute(select(Client).where(Client.id == row.client_id))
        client_row = client_result.scalar_one_or_none()
        if not client_row or not client_row.is_active:
            # Client inactive or missing — mark dead without usage rollback
            row.status = "dead"
            row.last_error = "Client inactive or missing"
            row.locked_at = None
            row.locked_by = None
            await db.commit()
            logger.warning(f"Outbox row {row.id} marked dead: client {row.client_id} inactive/missing")
            return

        client = _snapshot(client_row)
        events = [EventData(**event) for event in row.event_payload]
        context = row.request_context or {}
        event_names = _event_names(events)

        try:
            delivery_res = await deliver_events_to_platforms(client, events, context)
            primary_platform = delivery_res["primary_platform"]
            result = delivery_res["result"]

            row.status = "sent"
            row.sent_at = _now()
            row.locked_at = None
            row.locked_by = None
            row.last_error = None

            events_data = [event.model_dump(exclude_none=True) for event in events]
            for event_data in events_data:
                db.add(EventLog(**_event_log_kwargs(
                    client.id,
                    event_data,
                    "success",
                    context.get("ip_address"),
                    fb_response=json.dumps(result) if result else None,
                )))
            await db.commit()

            logger.info(f"[{client.name}] Outbox row {row.id} sent ({len(events)} events) via {primary_platform}.")

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
                await db.commit()
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
                await asyncio.gather(
                    *(process_outbox_row(row.id) for row in rows),
                    return_exceptions=True,
                )
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
