"""
Deferred Purchase Events Router
─────────────────────────────────
অর্ডার কনফার্ম/ক্যান্সেল হলে pending Purchase events ম্যানেজ করে।
কনফার্ম হলে event durable outbox queue-তে যায়; worker Facebook delivery করে।

Endpoints:
  POST /api/v1/events/confirm       — একটি অর্ডার কনফার্ম
  POST /api/v1/events/confirm/bulk  — একাধিক অর্ডার কনফার্ম
  POST /api/v1/events/cancel        — একটি অর্ডার ক্যান্সেল
  GET  /api/v1/events/pending       — pending events-এর লিস্ট
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_client, CachedClient
from app.models.pending_event import PendingEvent
from app.schemas.event import EventData
from app.services.event_worker import enqueue_events
from app.services.usage_service import check_and_reserve_usage

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Request/Response Schemas ────────────────────────────────────────────────

class ConfirmRequest(BaseModel):
    order_id: str


class BulkConfirmRequest(BaseModel):
    order_ids: List[str]


class CancelRequest(BaseModel):
    order_id: str


class PendingEventResponse(BaseModel):
    order_id: str
    event_name: str
    value: Optional[float] = None
    currency: Optional[str] = None
    status: str
    created_at: str
    age_hours: float


class ConfirmResponse(BaseModel):
    status: str
    order_id: str
    message: str


class BulkConfirmResponse(BaseModel):
    status: str
    confirmed: int
    failed: int
    details: list


class PendingListResponse(BaseModel):
    status: str
    total: int
    events: List[PendingEventResponse]


# ─── Helper: Queue confirmed event for worker delivery ───────────────────────

async def _queue_confirmed_event(
    client: CachedClient,
    pending: PendingEvent,
    db: AsyncSession,
) -> dict:
    """
    pending_events থেকে event data নিয়ে durable outbox-এ queue করে।
    event_time আপডেট করে (current time) — Facebook ৭ দিনের মধ্যের event চায়।
    """
    event_dict = pending.event_data.copy()

    # event_time আপডেট করো — current time
    event_dict["event_time"] = int(datetime.now(timezone.utc).timestamp())

    # EventData model-এ parse করো
    try:
        event = EventData(**event_dict)
    except Exception as e:
        logger.error(f"[{client.name}] Pending event parse error (order: {pending.order_id}): {e}")
        raise HTTPException(status_code=500, detail=f"Event data parse error: {e}")

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
    return event_dict


# ─── POST /events/confirm — Single Order Confirm ─────────────────────────────

@router.post(
    "/events/confirm",
    response_model=ConfirmResponse,
    summary="Confirm a pending Purchase event",
)
async def confirm_event(
    payload: ConfirmRequest,
    client: CachedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    একটি pending Purchase event কনফার্ম করে delivery queue-তে রাখে।
    Original user data (IP, UA, fbp, fbc) সহ পাঠানো হয়।
    """
    result = await db.execute(
        select(PendingEvent).where(
            and_(
                PendingEvent.client_id == client.id,
                PendingEvent.order_id == payload.order_id,
                PendingEvent.status == "pending",
            )
        ).with_for_update()
    )
    pending = result.scalar_one_or_none()

    if not pending:
        confirmed_result = await db.execute(
            select(PendingEvent).where(
                and_(
                    PendingEvent.client_id == client.id,
                    PendingEvent.order_id == payload.order_id,
                    PendingEvent.status == "confirmed",
                )
            )
        )
        if confirmed_result.scalar_one_or_none():
            return ConfirmResponse(
                status="success",
                order_id=payload.order_id,
                message="Purchase event was already confirmed.",
            )
        raise HTTPException(
            status_code=404,
            detail=f"Pending event not found: {payload.order_id}",
        )

    # Worker delivery queue-তে পাঠাও
    try:
        await _queue_confirmed_event(client, pending, db)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[{client.name}] Confirm queue failed ({payload.order_id}): {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Purchase event queue করতে সমস্যা: {e}",
        )

    # Status আপডেট
    pending.status = "confirmed"
    pending.confirmed_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"[{client.name}] Order confirmed & queued: {payload.order_id}")

    return ConfirmResponse(
        status="success",
        order_id=payload.order_id,
        message="Purchase event delivery queue-তে রাখা হয়েছে.",
    )


# ─── POST /events/confirm/bulk — Bulk Confirm ────────────────────────────────

@router.post(
    "/events/confirm/bulk",
    response_model=BulkConfirmResponse,
    summary="Confirm multiple pending Purchase events",
)
async def bulk_confirm_events(
    payload: BulkConfirmRequest,
    client: CachedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    একাধিক pending Purchase event একসাথে কনফার্ম করে delivery queue-তে রাখে।
    """
    if not payload.order_ids:
        raise HTTPException(status_code=400, detail="order_ids খালি!")

    if len(payload.order_ids) > 100:
        raise HTTPException(status_code=400, detail="একবারে সর্বোচ্চ ১০০টি অর্ডার কনফার্ম করা যায়।")

    # Fetch all pending events
    result = await db.execute(
        select(PendingEvent).where(
            and_(
                PendingEvent.client_id == client.id,
                PendingEvent.order_id.in_(payload.order_ids),
                PendingEvent.status == "pending",
            )
        ).with_for_update()
    )
    pending_events = result.scalars().all()

    found_ids = {p.order_id for p in pending_events}
    confirmed = 0
    failed = 0
    details = []

    for pending in pending_events:
        try:
            await _queue_confirmed_event(client, pending, db)
            pending.status = "confirmed"
            pending.confirmed_at = datetime.now(timezone.utc)
            confirmed += 1
            details.append({"order_id": pending.order_id, "status": "queued"})
        except HTTPException as e:
            failed += 1
            details.append({"order_id": pending.order_id, "status": "failed", "error": str(e.detail)})
            logger.error(f"[{client.name}] Bulk confirm queue rejected ({pending.order_id}): {e.detail}")
        except Exception as e:
            await db.rollback()
            logger.exception(f"[{client.name}] Bulk confirm queue failed ({pending.order_id})")
            raise HTTPException(status_code=500, detail=f"Bulk confirm queue failed: {e}") from None

    # Not found orders
    for oid in payload.order_ids:
        if oid not in found_ids:
            failed += 1
            details.append({"order_id": oid, "status": "not_found"})

    await db.commit()

    logger.info(f"[{client.name}] Bulk confirm queued: {confirmed} confirmed, {failed} failed")

    return BulkConfirmResponse(
        status="success",
        confirmed=confirmed,
        failed=failed,
        details=details,
    )


# ─── POST /events/cancel — Cancel ────────────────────────────────────────────

@router.post(
    "/events/cancel",
    response_model=ConfirmResponse,
    summary="Cancel a pending Purchase event",
)
async def cancel_event(
    payload: CancelRequest,
    client: CachedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Pending Purchase event ক্যান্সেল করে।
    Facebook-এ কোনো ডেটা পাঠানো হয় না।
    """
    result = await db.execute(
        select(PendingEvent).where(
            and_(
                PendingEvent.client_id == client.id,
                PendingEvent.order_id == payload.order_id,
                PendingEvent.status == "pending",
            )
        )
    )
    pending = result.scalar_one_or_none()

    if not pending:
        raise HTTPException(
            status_code=404,
            detail=f"Pending event not found: {payload.order_id}",
        )

    pending.status = "cancelled"
    await db.commit()

    logger.info(f"[{client.name}] ❌ Order cancelled: {payload.order_id}")

    return ConfirmResponse(
        status="success",
        order_id=payload.order_id,
        message="❌ Purchase event ক্যান্সেল হয়েছে। Facebook-এ কিছু পাঠানো হয়নি।",
    )


# ─── GET /events/pending — Pending List ──────────────────────────────────────

@router.get(
    "/events/pending",
    response_model=PendingListResponse,
    summary="List pending Purchase events",
)
async def list_pending_events(
    client: CachedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Pending Purchase events-এর paginated list"""
    offset = (page - 1) * limit

    # Total count
    from sqlalchemy import func as sql_func
    count_r = await db.execute(
        select(sql_func.count(PendingEvent.id)).where(
            and_(
                PendingEvent.client_id == client.id,
                PendingEvent.status == "pending",
            )
        )
    )
    total = count_r.scalar() or 0

    # Paginated results
    result = await db.execute(
        select(PendingEvent)
        .where(
            and_(
                PendingEvent.client_id == client.id,
                PendingEvent.status == "pending",
            )
        )
        .order_by(PendingEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    events = result.scalars().all()

    now = datetime.now(timezone.utc)
    event_list = []
    for e in events:
        event_data = e.event_data or {}
        custom_data = event_data.get("custom_data", {})
        created = e.created_at.replace(tzinfo=timezone.utc) if e.created_at.tzinfo is None else e.created_at
        age_hours = round((now - created).total_seconds() / 3600, 1)

        event_list.append(PendingEventResponse(
            order_id=e.order_id,
            event_name=event_data.get("event_name", "Purchase"),
            value=custom_data.get("value"),
            currency=custom_data.get("currency"),
            status=e.status,
            created_at=e.created_at.isoformat() if e.created_at else "",
            age_hours=age_hours,
        ))

    return PendingListResponse(
        status="success",
        total=total,
        events=event_list,
    )
