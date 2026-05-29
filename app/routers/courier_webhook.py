import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.client import Client
from app.models.pending_event import PendingEvent
from app.models.courier_order import CourierOrder
from app.dependencies import _snapshot
from app.routers.deferred_events import _queue_confirmed_event
from app.services.courier_service import CourierService
from app.schemas.event import EventData
from app.dependencies import CachedClient
from app.services.event_worker import enqueue_events
from app.services.event_quality import boost_event_quality
from app.services.usage_service import check_and_reserve_usage

logger = logging.getLogger(__name__)
router = APIRouter()

REQUIRE_COURIER_WEBHOOK_SECRET = os.getenv("REQUIRE_COURIER_WEBHOOK_SECRET", "true").lower() in ("1", "true", "yes")
COURIER_WEBHOOK_SECRET = os.getenv("COURIER_WEBHOOK_SECRET", "")


def _verify_courier_webhook_secret(request: Request) -> None:
    if not REQUIRE_COURIER_WEBHOOK_SECRET:
        return
    provided = (
        request.headers.get("x-courier-webhook-secret")
        or request.headers.get("x-webhook-secret")
        or request.query_params.get("secret")
        or ""
    )
    if not COURIER_WEBHOOK_SECRET or not hmac.compare_digest(provided, COURIER_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid courier webhook secret")

# ─── Helper: Queue Refund event for worker delivery ──────────────────────────
async def _queue_refund_event(
    client: CachedClient,
    pending: PendingEvent,
    db: AsyncSession,
) -> dict:
    """
    Purchase event data ক্লোন করে event_name 'Refund'-এ পরিবর্তন করে outbox-এ পাঠায়।
    """
    event_dict = pending.event_data.copy()
    event_dict.pop("raw_order_data", None)
    event_dict["event_name"] = "Refund"
    event_dict["event_time"] = int(datetime.now(timezone.utc).timestamp())

    try:
        event = EventData(**event_dict)
    except Exception as e:
        logger.error(f"[{client.name}] Refund event parse error (order: {pending.order_id}): {e}")
        return {}

    user_data = event_dict.get("user_data", {}) or {}
    boost_event_quality(
        event,
        ip_address=user_data.get("client_ip_address"),
        user_agent=user_data.get("client_user_agent") or "",
    )
    events_data = [event.model_dump(exclude_none=True)]
    reserved_keys = await check_and_reserve_usage(db, client, 1)
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
    logger.info(f"[{client.name}] Refund event queued for order {pending.order_id}")
    return event_dict

# ─── Common Status Processing Logic ──────────────────────────────────────────
async def process_courier_status_change(
    db: AsyncSession,
    courier_order: CourierOrder,
    new_raw_status: str
) -> None:
    provider = courier_order.courier_provider
    mapped_status = CourierService.map_status(provider, new_raw_status)
    old_status = courier_order.courier_status
    
    if old_status == mapped_status:
        return # No change
        
    # Update order details
    courier_order.courier_status = mapped_status
    
    # Append to history
    history = courier_order.status_history or []
    if not isinstance(history, list):
        history = []
    history.append({
        "status": mapped_status,
        "raw_status": new_raw_status,
        "time": datetime.now(timezone.utc).isoformat()
    })
    courier_order.status_history = history
    
    client_result = await db.execute(select(Client).where(Client.id == courier_order.client_id))
    client = client_result.scalar_one_or_none()
    
    pending_event = None
    if courier_order.pending_event_id:
        pending_result = await db.execute(
            select(PendingEvent).where(PendingEvent.id == courier_order.pending_event_id)
        )
        pending_event = pending_result.scalar_one_or_none()
        
    if client and pending_event:
        client_snapshot = _snapshot(client)
        
        # 1. Handle DELIVERED (trigger auto Purchase event)
        if mapped_status == "delivered" and not courier_order.purchase_event_sent:
            logger.info(f"Order {courier_order.order_id} delivered! Queueing auto Purchase event.")
            try:
                await _queue_confirmed_event(client_snapshot, pending_event, db)
                courier_order.purchase_event_sent = True
                courier_order.delivered_at = datetime.now(timezone.utc)
                pending_event.status = "confirmed"
                pending_event.confirmed_at = datetime.now(timezone.utc)  # analytics-এর জন্য জরুরি
                pending_event.portal_state = "confirmed"
                pending_event.is_confirmed = True
            except Exception as e:
                logger.error(f"Failed to queue auto Purchase event for delivered order {courier_order.order_id}: {e}")
                
        # 2. Handle RETURNED or CANCELLED (trigger Refund event to Facebook)
        elif mapped_status in ("returned", "cancelled"):
            # Refund event goes if it was already delivered/purchased, or if we want to log the cancel event.
            # Usually, Facebook expects Refund for already sent Purchases.
            if courier_order.purchase_event_sent:
                logger.info(f"Order {courier_order.order_id} was returned/cancelled after delivery. Queueing Refund event.")
                try:
                    await _queue_refund_event(client_snapshot, pending_event, db)
                except Exception as e:
                    logger.error(f"Failed to queue Refund event for order {courier_order.order_id}: {e}")
            
            pending_event.status = "cancelled"
            pending_event.portal_state = "cancelled"
            
    db.add(courier_order)
    if pending_event:
        db.add(pending_event)

# ─── Webhooks ────────────────────────────────────────────────────────────────

@router.post("/v1/webhook/steadfast")
async def steadfast_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    SteadFast Courier Webhook Endpoint.
    """
    _verify_courier_webhook_secret(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
        
    tracking_code = payload.get("tracking_code")
    status = payload.get("status")
    invoice = payload.get("invoice")
    
    if not tracking_code or not status:
        logger.warning(f"SteadFast webhook received invalid data: {payload}")
        return {"status": "ignored", "reason": "missing tracking_code or status"}
        
    logger.info(f"SteadFast webhook received for {tracking_code}: status={status}, invoice={invoice}")
    
    # Find matching courier order
    result = await db.execute(
        select(CourierOrder).where(CourierOrder.courier_tracking_id == str(tracking_code))
    )
    courier_order = result.scalar_one_or_none()
    
    if not courier_order:
        logger.warning(f"SteadFast courier order not found for tracking: {tracking_code}")
        return {"status": "ignored", "reason": "order not found"}
        
    await process_courier_status_change(db, courier_order, status)
    await db.commit()
    
    return {"status": "success"}

@router.post("/v1/webhook/pathao")
async def pathao_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Pathao Courier Webhook Endpoint.
    """
    _verify_courier_webhook_secret(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
        
    consignment_id = payload.get("consignment_id")
    status = payload.get("status")
    merchant_order_id = payload.get("merchant_order_id")
    
    if not consignment_id or not status:
        logger.warning(f"Pathao webhook received invalid data: {payload}")
        return {"status": "ignored", "reason": "missing consignment_id or status"}
        
    logger.info(f"Pathao webhook received for {consignment_id}: status={status}")
    
    # Find matching courier order
    result = await db.execute(
        select(CourierOrder).where(CourierOrder.courier_order_id == str(consignment_id))
    )
    courier_order = result.scalar_one_or_none()
    
    if not courier_order:
        logger.warning(f"Pathao courier order not found for consignment: {consignment_id}")
        return {"status": "ignored", "reason": "order not found"}
        
    await process_courier_status_change(db, courier_order, status)
    await db.commit()
    
    return {"status": "success"}
