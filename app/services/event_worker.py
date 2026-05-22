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
from app.services.event_quality import event_signal_flags
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


def _event_log_kwargs(client_id: int, event_data: dict, status: str, ip_address: str | None, **extra) -> dict:
    custom_data = event_data.get("custom_data") or {}
    utm_source = custom_data.get("utm_source")
    try:
        value = float(custom_data.get("value")) if custom_data.get("value") is not None else None
    except (TypeError, ValueError):
        value = None
    campaign_source = custom_data.get("campaign_source") or utm_source
    return {
        "client_id": client_id,
        "event_name": event_data.get("event_name") or "unknown",
        "event_id": event_data.get("event_id"),
        "event_count": 1,
        "status": status,
        "ip_address": ip_address,
        "emq_score": event_data.get("emq_score"),
        "value": value,
        "currency": custom_data.get("currency"),
        "campaign_source": campaign_source,
        "utm_source": utm_source,
        "utm_medium": custom_data.get("utm_medium"),
        "utm_campaign": custom_data.get("utm_campaign"),
        "utm_content": custom_data.get("utm_content"),
        "utm_term": custom_data.get("utm_term"),
        **event_signal_flags(event_data),
        **extra,
    }


async def _log_secondary_failure(
    client_id: int,
    channel: str,
    event_names: str,
    event_count: int,
    error_message: str,
    ip_address: str | None,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
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
        logger.warning(f"Secondary failure logging failed: {log_error}")


async def _log_secondary_success(
    client_id: int,
    channel: str,
    event_names: str,
    response_payload: object,
    ip_address: str | None,
) -> None:
    """Record non-primary platform delivery without inflating analytics totals."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(EventLog(
                client_id=client_id,
                event_name=f"{channel}:{event_names}"[:255],
                event_count=0,
                status="success",
                fb_response=json.dumps({
                    "channel": channel,
                    "response": response_payload,
                }, default=str)[:5000],
                ip_address=ip_address,
            ))
            await db.commit()
    except Exception as log_error:
        logger.warning(f"Secondary success logging failed: {log_error}")


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


async def _send_tiktok_secondary(client, events: list[EventData], event_names: str, ip_address: str | None) -> None:
    try:
        tiktok_result = await send_to_tiktok(client, events)
        if not tiktok_result or tiktok_result.get("code") not in (0, None):
            await _log_secondary_failure(
                client.id,
                "TikTok",
                event_names,
                len(events),
                tiktok_result or "TikTok send failed",
                ip_address,
            )
            return

        await _log_secondary_success(
            client.id,
            "TikTok",
            event_names,
            tiktok_result,
            ip_address,
        )
    except Exception as secondary_error:
        logger.warning(f"[{client.name}] TikTok secondary send failed: {secondary_error}")
        await _log_secondary_failure(
            client.id,
            "TikTok",
            event_names,
            len(events),
            str(secondary_error),
            ip_address,
        )


async def _send_ga4_secondary(
    client,
    events_data: list[dict],
    event_names: str,
    context: dict,
) -> None:
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
                client.id,
                "GA4",
                event_names,
                len(events_data),
                ga4_result.get("error") or ga4_result,
                context.get("ip_address"),
            )
    except Exception as secondary_error:
        logger.warning(f"[{client.name}] GA4 secondary send failed: {secondary_error}")
        await _log_secondary_failure(
            client.id,
            "GA4",
            event_names,
            len(events_data),
            str(secondary_error),
            context.get("ip_address"),
        )


async def _send_webhook_secondary(client, events_data: list[dict], context: dict) -> None:
    for event_data in events_data:
        try:
            sent = await send_webhook(
                client.webhook_url,
                "event.sent",
                {
                    "client_name": client.name,
                    "event_name": event_data.get("event_name"),
                    "event_id": event_data.get("event_id"),
                    "custom_data": event_data.get("custom_data", {}),
                },
            )
            if not sent:
                await _log_secondary_failure(
                    client.id,
                    "Webhook",
                    event_data.get("event_name") or "unknown",
                    1,
                    "Webhook send failed",
                    context.get("ip_address"),
                )
        except Exception as secondary_error:
            logger.warning(f"[{client.name}] Outbound webhook failed: {secondary_error}")
            await _log_secondary_failure(
                client.id,
                "Webhook",
                event_data.get("event_name") or "unknown",
                1,
                str(secondary_error),
                context.get("ip_address"),
            )


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
            facebook_enabled = bool(getattr(client, "enable_facebook", True) and client.pixel_id and client.access_token)
            tiktok_enabled = bool(getattr(client, "enable_tiktok", True) and client.tiktok_pixel_id and client.tiktok_access_token)
            ga4_enabled = bool(getattr(client, "enable_ga4", True) and client.ga4_measurement_id and client.ga4_api_secret)
            webhook_enabled = bool(client.webhook_url)

            if not any([facebook_enabled, tiktok_enabled, ga4_enabled, webhook_enabled]):
                raise RuntimeError("No delivery platform enabled for this client")

            result = None
            if facebook_enabled:
                result = await send_to_facebook(client, events)

            events_data = [event.model_dump(exclude_none=True) for event in events]
            primary_tiktok_sent = False
            primary_ga4_sent = False
            if not facebook_enabled and tiktok_enabled:
                tiktok_result = await send_to_tiktok(client, events)
                if not tiktok_result or tiktok_result.get("code") not in (0, None):
                    raise RuntimeError(f"TikTok send failed: {tiktok_result}")
                primary_tiktok_sent = True

            if not facebook_enabled and not tiktok_enabled and ga4_enabled:
                ga4_result = await send_to_ga4(
                    events=events_data,
                    measurement_id=client.ga4_measurement_id,
                    api_secret=client.ga4_api_secret,
                    cookies=context.get("cookies") or {},
                    ip_address=context.get("ip_address"),
                    user_agent=context.get("user_agent") or "",
                )
                if ga4_result and not ga4_result.get("ok", True):
                    raise RuntimeError(f"GA4 send failed: {ga4_result.get('error') or ga4_result}")
                primary_ga4_sent = True

            row.status = "sent"
            row.sent_at = _now()
            row.locked_at = None
            row.locked_by = None
            row.last_error = None

            for event_data in events_data:
                db.add(EventLog(**_event_log_kwargs(
                    client.id,
                    event_data,
                    "success",
                    context.get("ip_address"),
                    fb_response=json.dumps(result) if result else None,
                )))
            await db.commit()

            secondary_tasks = []
            if tiktok_enabled and not primary_tiktok_sent:
                secondary_tasks.append(
                    _send_tiktok_secondary(client, events, event_names, context.get("ip_address"))
                )

            if ga4_enabled and not primary_ga4_sent:
                secondary_tasks.append(
                    _send_ga4_secondary(client, events_data, event_names, context)
                )

            if webhook_enabled:
                secondary_tasks.append(_send_webhook_secondary(client, events_data, context))

            if secondary_tasks:
                await asyncio.gather(*secondary_tasks)

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
