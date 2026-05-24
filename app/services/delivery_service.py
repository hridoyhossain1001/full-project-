import asyncio
import json
import logging
from app.database import AsyncSessionLocal
from app.models.event_log import EventLog
from app.schemas.event import EventData
from app.services.capi_service import send_to_facebook
from app.services.ga4_service import send_to_ga4
from app.services.tiktok_service import send_to_tiktok
from app.services.webhook_service import send_webhook

logger = logging.getLogger(__name__)

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

        if tiktok_result.get("sent_count") == 0:
            logger.info(
                f"[{client.name}] TikTok secondary skipped unsupported event(s): {event_names}"
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

async def deliver_events_to_platforms(
    client,
    events: list[EventData],
    context: dict,
) -> dict:
    """
    Deliver events to enabled ad/analytics platforms.
    Determines primary and secondary platforms based on active settings.
    Raises exceptions if the primary delivery platform fails.
    Fires secondary deliveries as parallel background tasks.
    """
    event_names = ", ".join(sorted({event.event_name for event in events}))
    events_data = [event.model_dump(exclude_none=True) for event in events]

    facebook_enabled = bool(getattr(client, "enable_facebook", True) and client.pixel_id and client.access_token)
    tiktok_enabled = bool(getattr(client, "enable_tiktok", True) and client.tiktok_pixel_id and client.tiktok_access_token)
    ga4_enabled = bool(getattr(client, "enable_ga4", True) and client.ga4_measurement_id and client.ga4_api_secret)
    webhook_enabled = bool(client.webhook_url)

    if not any([facebook_enabled, tiktok_enabled, ga4_enabled, webhook_enabled]):
        raise RuntimeError("No delivery platform enabled for this client")

    result = None
    primary_platform = None
    primary_tiktok_sent = False
    primary_ga4_sent = False

    if facebook_enabled:
        result = await send_to_facebook(client, events)
        primary_platform = "Facebook"
    elif tiktok_enabled:
        tiktok_result = await send_to_tiktok(client, events)
        if not tiktok_result or tiktok_result.get("code") not in (0, None):
            raise RuntimeError(f"TikTok send failed: {tiktok_result}")
        result = tiktok_result
        primary_tiktok_sent = True
        primary_platform = "TikTok"
    elif ga4_enabled:
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
        result = ga4_result
        primary_ga4_sent = True
        primary_platform = "GA4"
    elif webhook_enabled:
        webhook_errors = []
        for event_data in events_data:
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
                webhook_errors.append(event_data.get("event_name") or "unknown")
        if webhook_errors:
            raise RuntimeError(f"Webhook send failed for: {', '.join(webhook_errors)}")
        result = {"ok": True, "sent_count": len(events_data)}
        primary_platform = "Webhook"

    # Fire secondary sends in parallel as background tasks
    secondary_tasks = []
    if tiktok_enabled and not primary_tiktok_sent:
        secondary_tasks.append(
            _send_tiktok_secondary(client, events, event_names, context.get("ip_address"))
        )

    if ga4_enabled and not primary_ga4_sent:
        secondary_tasks.append(
            _send_ga4_secondary(client, events_data, event_names, context)
        )

    if webhook_enabled and primary_platform != "Webhook":
        secondary_tasks.append(_send_webhook_secondary(client, events_data, context))

    # Fire secondary sends as true background tasks — don't block the outbox worker
    tasks = []
    for coro in secondary_tasks:
        task = asyncio.create_task(coro)
        task.add_done_callback(
            lambda t: logger.error(f"Secondary send failed: {t.exception()}")
            if t.exception() else None
        )
        tasks.append(task)

    return {
        "primary_platform": primary_platform,
        "result": result,
        "_tasks": tasks,
    }
