"""
WooCommerce Webhook Router
────────────────────────────
WordPress-এর বিল্ট-ইন Webhook সিস্টেম দিয়ে অর্ডার স্ট্যাটাস চেঞ্জ রিসিভ করে।
প্লাগইন ব্যবহার না করলেও এই endpoint দিয়ে Deferred Purchase কনফার্ম করে
durable outbox queue-তে পাঠানো যায়।

Endpoints:
  POST /api/v1/webhook/woocommerce  — WooCommerce Webhook রিসিভ করে
"""

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import Client
from app.models.pending_event import PendingEvent
from app.schemas.event import EventData
from app.services.event_worker import enqueue_events
from app.services.usage_service import check_and_reserve_usage
from app.dependencies import CachedClient, _snapshot

logger = logging.getLogger(__name__)
router = APIRouter()

REQUIRE_WC_WEBHOOK_SIGNATURE = os.getenv("REQUIRE_WC_WEBHOOK_SIGNATURE", "true").lower() in ("1", "true", "yes")


def _verify_wc_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify WooCommerce X-WC-Webhook-Signature (base64 HMAC-SHA256)."""
    if not signature or not secret:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


async def _get_client_by_api_key(api_key: str, db: AsyncSession):
    """API Key দিয়ে ক্লায়েন্ট খুঁজে বের করে।"""
    result = await db.execute(
        select(Client).where(
            and_(Client.api_key == api_key, Client.is_active == True)
        )
    )
    return result.scalar_one_or_none()


@router.post(
    "/webhook/woocommerce",
    summary="WooCommerce Webhook Receiver",
    description="WooCommerce order status change webhook রিসিভ করে এবং pending Purchase event কনফার্ম করে।",
)
async def woocommerce_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    WooCommerce Webhook Format:
    Header: X-WC-Webhook-Topic: order.updated / order.completed
    Header: X-API-Key: <client_api_key>
    Body: Full WooCommerce order JSON
    """

    # ─── API Key Authentication ───────────────────────────────────────
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key missing")

    client_row = await _get_client_by_api_key(api_key, db)
    if not client_row:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    client = _snapshot(client_row)
    raw_body = await request.body()
    signature = request.headers.get("x-wc-webhook-signature", "")
    webhook_secret = os.getenv("WC_WEBHOOK_SECRET", "") or api_key
    if REQUIRE_WC_WEBHOOK_SIGNATURE and not _verify_wc_signature(raw_body, signature, webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid WooCommerce webhook signature")

    # ─── Parse Webhook Body ───────────────────────────────────────────
    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # WooCommerce sends order data directly
    order_id = body.get("id") or body.get("order_id")
    status = body.get("status", "")

    if not order_id:
        raise HTTPException(status_code=400, detail="Order ID not found in payload")

    logger.info(f"[{client.name}] 📬 WooCommerce webhook: order #{order_id}, status: {status}")

    # ─── Only process completed/processing orders ─────────────────────
    if status not in ("completed", "processing"):
        return {
            "status": "ignored",
            "message": f"Order #{order_id} status '{status}' — no action needed",
        }

    # ─── Find pending event for this order ────────────────────────────
    # Try both 'wc_purchase_<id>' (plugin format) and raw order_id
    possible_ids = [f"wc_purchase_{order_id}", str(order_id)]

    pending = None
    for pid in possible_ids:
        result = await db.execute(
            select(PendingEvent).where(
                and_(
                    PendingEvent.client_id == client.id,
                    PendingEvent.order_id == pid,
                    PendingEvent.status == "pending",
                )
            ).with_for_update()
        )
        pending = result.scalar_one_or_none()
        if pending:
            break

    if not pending:
        confirmed_result = await db.execute(
            select(PendingEvent).where(
                and_(
                    PendingEvent.client_id == client.id,
                    PendingEvent.order_id.in_(possible_ids),
                    PendingEvent.status == "confirmed",
                )
            )
        )
        if confirmed_result.scalar_one_or_none():
            return {
                "status": "success",
                "order_id": str(order_id),
                "message": "Purchase event was already confirmed.",
            }
        return {
            "status": "skipped",
            "message": f"No pending Purchase event found for order #{order_id}",
        }

    # ─── Queue confirmed purchase for worker delivery ────────────────
    event_dict = pending.event_data.copy()
    event_dict["event_time"] = int(datetime.now(timezone.utc).timestamp())

    try:
        event = EventData(**event_dict)
        events_data = [event.model_dump(exclude_none=True)]
        reserved_keys = await check_and_reserve_usage(db, client, 1)
        user_data = event_dict.get("user_data", {}) or {}
        await enqueue_events(
            db,
            client_id=client.id,
            events_data=events_data,
            request_context={
                "ip_address": user_data.get("client_ip_address"),
                "user_agent": user_data.get("client_user_agent") or "",
                "cookies": {},
            },
            usage_reserved=reserved_keys,
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[{client.name}] Webhook confirm queue failed (order #{order_id}): {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Purchase event queue failed: {e}",
        ) from None

    # ─── Update pending status ────────────────────────────────────────
    pending.status = "confirmed"
    pending.confirmed_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"[{client.name}] Webhook confirmed order #{order_id} queued for delivery")

    return {
        "status": "success",
        "order_id": str(order_id),
        "message": "Purchase event confirmed and queued for delivery!",
    }
