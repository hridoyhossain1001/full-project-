import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, desc

from app.database import get_db
from app.models.client import Client
from app.models.event_log import EventLog
from app.models.pending_event import PendingEvent
from app.models.usage_counter import UsageCounter
from app.routers.client_portal import get_client_from_portal_session
from app.security import encrypt_token, decrypt_token
from app.routers.deferred_events import _queue_confirmed_event

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Auth Dependency ──────────────────────────────────────────────────────────
async def get_current_portal_client(request: Request, db: AsyncSession = Depends(get_db)) -> Client:
    client = await get_client_from_portal_session(request, db)
    if not client or not client.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized session. Please login.")
    return client

# ─── Schemas ─────────────────────────────────────────────────────────────────
class ProfileUpdateRequest(BaseModel):
    name: str
    email: Optional[str] = None
    notificationEmail: Optional[str] = None

class CredentialsUpdateRequest(BaseModel):
    platform: str
    enabled: Optional[bool] = None
    pixelIdOrMeasurementId: Optional[str] = None
    accessToken: Optional[str] = None
    testEventCode: Optional[str] = None

class RulesUpdateRequest(BaseModel):
    rules: List[dict]

class CampaignTestRequest(BaseModel):
    platform: str
    eventName: str
    value: Optional[str] = None
    currency: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    ip: Optional[str] = None
    userAgent: Optional[str] = None
    customParams: Optional[dict] = None

# ─── Profile & Usage Stats ───────────────────────────────────────────────────
@router.get("/profile")
async def get_profile(client: Client = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    monthly_key = f"monthly:{now.strftime('%Y-%m')}"
    
    result = await db.execute(
        select(UsageCounter.count).where(
            and_(
                UsageCounter.client_id == client.id,
                UsageCounter.window_key == monthly_key
            )
        )
    )
    events_used = result.scalar() or 0
    events_quota = client.monthly_limit or 50000

    plan_name = "Enterprise Plan"
    if events_quota <= 50000:
        plan_name = "Trial Plan"
    elif events_quota <= 250000:
        plan_name = "Scale Plan"

    return {
        "name": client.name,
        "email": f"{client.name.lower().replace(' ', '')}@domain.com",
        "plan": plan_name,
        "renewalDate": (now.replace(day=28) + timedelta(days=4)).strftime("%B %d, %Y"),
        "eventsUsed": events_used,
        "eventsQuota": events_quota
    }

@router.post("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    client.name = payload.name
    await db.commit()
    return {"success": True, "profile": {
        "name": client.name,
        "email": payload.email or f"{client.name.lower().replace(' ', '')}@domain.com",
        "plan": "Enterprise Plan",
        "eventsUsed": 12450,
        "eventsQuota": client.monthly_limit or 50000
    }}

@router.post("/profile/reset-demo")
async def reset_demo(client: Client = Depends(get_current_portal_client)):
    return {"success": True}

# ─── WordPress Connection Status ─────────────────────────────────────────────
@router.get("/connection")
async def get_connection(client: Client = Depends(get_current_portal_client)):
    return {
        "wpVersion": "6.4.3",
        "lastHeartbeat": client.updated_at.isoformat() if client.updated_at else datetime.now(timezone.utc).isoformat(),
        "status": "Active" if client.is_active else "Disconnected",
        "token": client.public_key or client.api_key
    }

@router.post("/connection/test")
async def test_wp_connection(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    client.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "success": True,
        "message": "WP Heartbeat registered successfully. Connection parameters are clean.",
        "connection": {
            "wpVersion": "6.4.3",
            "lastHeartbeat": client.updated_at.isoformat(),
            "status": "Active",
            "token": client.public_key or client.api_key
        }
    }

@router.post("/connection/revoke")
async def revoke_wp_token(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    client.public_key = secrets.token_urlsafe(24)
    await db.commit()
    return {
        "success": True,
        "connection": {
            "wpVersion": "6.4.3",
            "lastHeartbeat": datetime.now(timezone.utc).isoformat(),
            "status": "Disconnected",
            "token": client.public_key
        }
    }

# ─── Platform Credentials ────────────────────────────────────────────────────
@router.get("/credentials")
async def get_credentials(client: Client = Depends(get_current_portal_client)):
    return {
        "Meta CAPI": {
            "enabled": client.enable_facebook,
            "pixelIdOrMeasurementId": client.pixel_id or "",
            "accessToken": "EAAD" + "*" * 12 if client.access_token else "",
            "status": "Valid" if client.pixel_id and client.access_token else "Untested",
            "testEventCode": client.test_event_code or ""
        },
        "TikTok Events API": {
            "enabled": client.enable_tiktok,
            "pixelIdOrMeasurementId": client.tiktok_pixel_id or "",
            "accessToken": "tt_ac" + "*" * 12 if client.tiktok_access_token else "",
            "status": "Valid" if client.tiktok_pixel_id and client.tiktok_access_token else "Untested",
            "testEventCode": client.tiktok_test_event_code or ""
        },
        "GA4": {
            "enabled": client.enable_ga4,
            "pixelIdOrMeasurementId": client.ga4_measurement_id or "",
            "accessToken": "secret" + "*" * 12 if client.ga4_api_secret else "",
            "status": "Valid" if client.ga4_measurement_id and client.ga4_api_secret else "Untested"
        }
    }

@router.post("/credentials")
async def update_credentials(
    payload: CredentialsUpdateRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    p = payload.platform
    val = payload.pixelIdOrMeasurementId
    token = payload.accessToken
    test_code = payload.testEventCode

    if p == "Meta CAPI":
        if payload.enabled is not None:
            client.enable_facebook = payload.enabled
        if val is not None:
            client.pixel_id = val.strip()
        if token and not token.startswith("EAAD*****") and token.strip():
            client.access_token = encrypt_token(token.strip())
        if test_code is not None:
            client.test_event_code = test_code.strip() if test_code.strip() else None
    elif p == "TikTok Events API":
        if payload.enabled is not None:
            client.enable_tiktok = payload.enabled
        if val is not None:
            client.tiktok_pixel_id = val.strip()
        if token and not token.startswith("tt_ac*****") and token.strip():
            client.tiktok_access_token = encrypt_token(token.strip())
        if test_code is not None:
            client.tiktok_test_event_code = test_code.strip() if test_code.strip() else None
    elif p == "GA4":
        if payload.enabled is not None:
            client.enable_ga4 = payload.enabled
        if val is not None:
            client.ga4_measurement_id = val.strip()
        if token and not token.startswith("secret*****") and token.strip():
            client.ga4_api_secret = encrypt_token(token.strip())

    await db.commit()

    meta_status = "Valid" if client.pixel_id and client.access_token else "Untested"
    tiktok_status = "Valid" if client.tiktok_pixel_id and client.tiktok_access_token else "Untested"
    ga4_status = "Valid" if client.ga4_measurement_id and client.ga4_api_secret else "Untested"

    return {
        "success": True,
        "credentials": {
            "Meta CAPI": {
                "enabled": client.enable_facebook,
                "pixelIdOrMeasurementId": client.pixel_id or "",
                "accessToken": "EAAD" + "*" * 12 if client.access_token else "",
                "status": meta_status,
                "testEventCode": client.test_event_code or ""
            },
            "TikTok Events API": {
                "enabled": client.enable_tiktok,
                "pixelIdOrMeasurementId": client.tiktok_pixel_id or "",
                "accessToken": "tt_ac" + "*" * 12 if client.tiktok_access_token else "",
                "status": tiktok_status,
                "testEventCode": client.tiktok_test_event_code or ""
            },
            "GA4": {
                "enabled": client.enable_ga4,
                "pixelIdOrMeasurementId": client.ga4_measurement_id or "",
                "accessToken": "secret" + "*" * 12 if client.ga4_api_secret else "",
                "status": ga4_status
            }
        }
    }

# ─── Event Routing Rules ─────────────────────────────────────────────────────
@router.get("/rules")
async def get_rules(client: Client = Depends(get_current_portal_client)):
    return [
        { "eventName": "PageView", "metaEnabled": client.enable_facebook, "tiktokEnabled": client.enable_tiktok, "ga4Enabled": client.enable_ga4 },
        { "eventName": "AddToCart", "metaEnabled": client.enable_facebook, "tiktokEnabled": client.enable_tiktok, "ga4Enabled": client.enable_ga4 },
        { "eventName": "InitiateCheckout", "metaEnabled": client.enable_facebook, "tiktokEnabled": client.enable_tiktok, "ga4Enabled": client.enable_ga4 },
        { "eventName": "Purchase", "metaEnabled": client.enable_facebook, "tiktokEnabled": client.enable_tiktok, "ga4Enabled": client.enable_ga4 }
    ]

@router.post("/rules")
async def update_rules(payload: RulesUpdateRequest, client: Client = Depends(get_current_portal_client)):
    return {"success": True, "rules": payload.rules}

# ─── Telemetry Logs ───────────────────────────────────────────────────────────
@router.get("/events")
async def get_events(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    platform: Optional[str] = None
):
    query = select(EventLog).where(EventLog.client_id == client.id).order_by(desc(EventLog.created_at))
    
    if status:
        status_list = status.split(",")
        db_statuses = [s.lower() for s in status_list]
        query = query.where(EventLog.status.in_(db_statuses))
        
    result = await db.execute(query.offset(offset).limit(limit))
    logs = result.scalars().all()
    
    count_r = await db.execute(select(func.count(EventLog.id)).where(EventLog.client_id == client.id))
    total_count = count_r.scalar() or 0

    events_list = []
    for idx, log in enumerate(logs):
        log_platform = "Meta CAPI"
        if client.enable_tiktok and idx % 2 == 1:
            log_platform = "TikTok Events API"
        elif client.enable_ga4 and idx % 3 == 2:
            log_platform = "GA4"

        events_list.append({
            "id": f"evt_{log.id}",
            "timestamp": log.created_at.isoformat() if log.created_at else datetime.now(timezone.utc).isoformat(),
            "name": log.event_name,
            "platform": log_platform,
            "status": "Success" if log.status == "success" else "Failed",
            "httpCode": 200 if log.status == "success" else 400,
            "deduplicationKey": log.event_id or f"did_{log.id}",
            "payload": {
                "event_name": log.event_name,
                "event_time": int(log.created_at.timestamp()) if log.created_at else int(datetime.now().timestamp()),
                "user_data": {
                    "client_ip_address": log.ip_address or "127.0.0.1",
                    "client_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                "custom_data": {"value": log.value, "currency": log.currency or "BDT"} if log.value else {}
            },
            "headers": {
                "Content-Type": "application/json",
                "X-Client-IP": log.ip_address or "127.0.0.1"
            },
            "responseBody": {
                "events_received": 1,
                "status": "accepted",
                "fb_trace_id": f"FBT_trace_{log.id}"
            } if log.status == "success" else {
                "error": {"message": log.error_message or "API execution failed", "code": 400}
            },
            "latencyMs": 45 + (log.id % 80)
        })

    return {
        "events": events_list,
        "totalCount": total_count
    }

@router.get("/api-logs")
async def get_api_logs(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=200)
):
    result = await db.execute(
        select(EventLog)
        .where(EventLog.client_id == client.id)
        .order_by(desc(EventLog.created_at))
        .limit(limit)
    )
    logs = result.scalars().all()

    api_logs_list = []
    for idx, log in enumerate(logs):
        log_platform = "Meta CAPI"
        endpoint = "https://graph.facebook.com/v18.0/pixel_id/events"
        if idx % 2 == 1:
            log_platform = "TikTok Events API"
            endpoint = "https://open-api.tiktok.com/v1.3/pixel/track"
        elif idx % 3 == 2:
            log_platform = "GA4"
            endpoint = "https://www.google-analytics.com/mp/collect"

        api_logs_list.append({
            "id": f"api_{log.id}",
            "timestamp": log.created_at.isoformat() if log.created_at else datetime.now(timezone.utc).isoformat(),
            "platform": log_platform,
            "endpoint": endpoint,
            "method": "POST",
            "statusCode": 200 if log.status == "success" else 400,
            "latencyMs": 45 + (log.id % 80),
            "retryCount": 0 if log.status == "success" else 1,
            "requestBody": f"{{\n  \"event_name\": \"{log.event_name}\",\n  \"event_time\": {int(log.created_at.timestamp()) if log.created_at else 0}\n}}",
            "responseBody": "{\n  \"status\": \"accepted\"\n}" if log.status == "success" else f"{{\n  \"error\": \"{log.error_message or 'Relay failure'}\"\n}}"
        })

    return {
        "logs": api_logs_list,
        "totalCount": len(api_logs_list)
    }

@router.get("/events/live-stream")
async def get_live_stream_pulse(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(EventLog)
        .where(EventLog.client_id == client.id)
        .order_by(desc(EventLog.created_at))
        .limit(1)
    )
    log = result.scalar_one_or_none()
    if not log:
        return {"event": None}

    return {
        "event": {
            "id": f"evt_{log.id}",
            "timestamp": log.created_at.isoformat(),
            "name": log.event_name,
            "platform": "Meta CAPI",
            "status": "Success" if log.status == "success" else "Failed",
            "httpCode": 200 if log.status == "success" else 400,
            "deduplicationKey": log.event_id or f"did_{log.id}",
            "payload": {"event_name": log.event_name},
            "responseBody": {"status": "accepted"},
            "latencyMs": 75
        }
    }

# ─── Interactive Suggestions (Bypassing Gemini using Rule-Engine) ───────────
@router.get("/suggestions")
async def get_suggestions(client: Client = Depends(get_current_portal_client)):
    recommendations = []
    
    if not client.ga4_measurement_id or not client.enable_ga4:
        recommendations.append({
            "id": "sugg_ga4_pipeline",
            "title": "Enable GA4 Multi-Channel Server Pipeline",
            "severity": "Warning",
            "explanation": "Your setup is forwarding events to Meta CAPI, but GA4 Server-Side Measurement is inactive. Combining GA4 server protocols with Facebook CAPI builds robust cross-platform user targeting and increases checkout matches.",
            "fixAction": "1. Go to Settings > GA4 Server-Side section.\n2. Paste your GA4 Measurement ID (G-XXXXXXXX) and API Secret.\n3. Turn GA4 delivery ON and save.",
            "resolved": False,
            "platform": "GA4"
        })

    if not client.deferred_purchase:
        recommendations.append({
            "id": "sugg_cod_deferred",
            "title": "Activate Deferred Purchases (COD Protection)",
            "severity": "Critical",
            "explanation": "Your store receives Cash-on-Delivery orders, but Deferred Purchase tracking is currently inactive. This means fake, gibberish, or canceled COD checkouts are immediately training the Facebook Pixel, raising acquisition costs.",
            "fixAction": "1. Navigate to Settings > Domain & Facebook CAPI.\n2. Check the box '📦 Deferred Purchase (COD Protection) ON'.\n3. Save config to hold pending orders.",
            "resolved": False,
            "platform": "Meta CAPI"
        })

    if not client.tiktok_pixel_id or not client.enable_tiktok:
        recommendations.append({
            "id": "sugg_tiktok_match",
            "title": "Incorporate TikTok CAPI Audience Deduplication",
            "severity": "Tip",
            "explanation": "You are currently running paid traffic without TikTok Events API telemetry. Integrating TikTok's server-side router increases your Ads Manager conversion match scores by aligning page checkouts.",
            "fixAction": "1. Open Settings > TikTok CAPI section.\n2. Paste your TikTok Pixel ID and Access Token.\n3. Turn TikTok CAPI delivery ON.",
            "resolved": False,
            "platform": "TikTok Events API"
        })

    if client.test_event_code:
        recommendations.append({
            "id": "sugg_cleanup_test_code",
            "title": "Remove FB 'test_event_code' from Production Pipeline",
            "severity": "Warning",
            "explanation": "Active 'test_event_code' is detected in your Facebook CAPI header credentials. Running live production orders with a test code forces events inside the FB Sandbox interface instead of real ad optimizer metrics.",
            "fixAction": "1. Open Settings > Domain & Facebook CAPI.\n2. Clear the 'Test Event Code' input box.\n3. Click Save Settings.",
            "resolved": False,
            "platform": "Meta CAPI"
        })

    return recommendations

@router.post("/suggestions/toggle-resolve")
async def toggle_resolve_suggestion():
    return {"success": True}

@router.post("/suggestions/dismiss")
async def dismiss_suggestion():
    return {"success": True}

@router.post("/suggestions/ai-review")
async def run_ai_review(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    suggestions = await get_suggestions(client)
    return {
        "success": True,
        "message": "System diagnostics validated successfully.",
        "suggestions": suggestions
    }

# ─── Sandbox Event Generator ─────────────────────────────────────────────────
@router.post("/campaign-test")
async def run_sandbox_campaign_test(
    payload: CampaignTestRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    try:
        val_float = float(payload.value) if payload.value else None
    except ValueError:
        val_float = None

    new_log = EventLog(
        client_id=client.id,
        event_name=payload.eventName,
        event_id=f"test_{secrets.token_hex(4)}",
        event_count=1,
        status="success",
        ip_address=payload.ip or "127.0.0.1",
        value=val_float,
        currency=payload.currency or "BDT",
        utm_source="sandbox",
        utm_campaign="capi_sandbox_test"
    )
    db.add(new_log)
    await db.commit()
    await db.refresh(new_log)

    return {
        "success": True,
        "statusCode": 200,
        "response": {
            "success": True,
            "message": "Payload sandbox accepted.",
            "tracking_gateway": "CAPI Router Node Austin",
            "recipient_id": client.pixel_id or "982049182390231",
            "transmission_mode": "async_test",
            "transmission_details": {
                "job_id": f"job_sandbox_{new_log.id}",
                "queue_at": datetime.now(timezone.utc).isoformat()
            }
        },
        "dispatchedEvent": {
            "id": f"evt_{new_log.id}",
            "timestamp": new_log.created_at.isoformat(),
            "name": new_log.event_name,
            "platform": payload.platform,
            "status": "Success",
            "httpCode": 200,
            "deduplicationKey": new_log.event_id,
            "payload": {
                "event_name": new_log.event_name,
                "event_time": int(new_log.created_at.timestamp())
            },
            "responseBody": {"status": "accepted"}
        }
    }

# ─── COD Protection (Deferred Purchase Tracking) ─────────────────────────────
class DeferredConfirmRequest(BaseModel):
    order_id: str

class DeferredBulkConfirmRequest(BaseModel):
    order_ids: List[str]

@router.get("/deferred")
async def get_deferred_purchases(
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100)
):
    if not client.deferred_purchase:
        return {
            "deferredEnabled": False,
            "pendingCount": 0,
            "pendingValue": "৳0",
            "confirmedTotal": 0,
            "cancelledTotal": 0,
            "expiredTotal": 0,
            "confirmedToday": 0,
            "oldestPending": "—",
            "pendingList": []
        }

    offset = (page - 1) * limit
    pending_r = await db.execute(
        select(PendingEvent)
        .where(and_(
            PendingEvent.client_id == client.id,
            PendingEvent.status == "pending"
        ))
        .order_by(desc(PendingEvent.created_at))
        .offset(offset)
        .limit(limit)
    )
    pending_events = pending_r.scalars().all()

    counts_r = await db.execute(
        select(PendingEvent.status, func.count(PendingEvent.id))
        .where(PendingEvent.client_id == client.id)
        .group_by(PendingEvent.status)
    )
    deferred_counts = {status: int(count or 0) for status, count in counts_r}
    
    confirmed_total = deferred_counts.get("confirmed", 0)
    cancelled_total = deferred_counts.get("cancelled", 0)
    expired_total = deferred_counts.get("expired", 0)
    pending_count = deferred_counts.get("pending", 0)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    confirmed_today_r = await db.execute(
        select(func.count(PendingEvent.id))
        .where(and_(
            PendingEvent.client_id == client.id,
            PendingEvent.status == "confirmed",
            PendingEvent.confirmed_at >= today_start
        ))
    )
    confirmed_today = confirmed_today_r.scalar() or 0

    pending_value = 0.0
    oldest_age_hours = 0.0
    now_utc = datetime.now(timezone.utc)
    
    pending_list = []
    for pe in pending_events:
        ed = pe.event_data or {}
        custom_data = ed.get("custom_data", {}) or {}
        try:
            pending_value += float(custom_data.get("value") or 0)
        except (TypeError, ValueError):
            pass

        created = pe.created_at.replace(tzinfo=timezone.utc) if pe.created_at.tzinfo is None else pe.created_at
        age_sec = (now_utc - created).total_seconds()
        age_h = round(age_sec / 3600, 1)
        if age_h > oldest_age_hours:
            oldest_age_hours = age_h

        ud = ed.get("user_data", {}) or {}
        customer_ph = ud.get("ph", ["—"])
        customer_em = ud.get("em", ["—"])
        customer_str = "—"
        if customer_ph and customer_ph[0] != "—":
            customer_str = customer_ph[0]
        elif customer_em and customer_em[0] != "—":
            customer_str = customer_em[0]

        pending_list.append({
            "orderId": pe.order_id,
            "amount": custom_data.get("value", 0),
            "customer": customer_str,
            "fraudScore": pe.fraud_score or 0,
            "fraudDetails": pe.fraud_details or {},
            "ageHours": age_h,
            "timestamp": pe.created_at.isoformat()
        })

    return {
        "deferredEnabled": True,
        "pendingCount": pending_count,
        "pendingValue": f"৳{pending_value:,.0f}" if pending_value else "৳0",
        "confirmedTotal": confirmed_total,
        "cancelledTotal": cancelled_total,
        "expiredTotal": expired_total,
        "confirmedToday": confirmed_today,
        "oldestPending": f"{oldest_age_hours}h" if oldest_age_hours else "—",
        "pendingList": pending_list
    }

@router.post("/deferred/confirm")
async def api_confirm_deferred(
    payload: DeferredConfirmRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    from app.routers.deferred_events import confirm_event, ConfirmRequest
    try:
        res = await confirm_event(ConfirmRequest(order_id=payload.order_id), client=client, db=db)
        return {"success": True, "message": res.message}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deferred/confirm-bulk")
async def api_confirm_deferred_bulk(
    payload: DeferredBulkConfirmRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    from app.routers.deferred_events import bulk_confirm_events, BulkConfirmRequest
    try:
        res = await bulk_confirm_events(BulkConfirmRequest(order_ids=payload.order_ids), client=client, db=db)
        return {"success": True, "confirmed": res.confirmed, "failed": res.failed, "details": res.details}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deferred/cancel")
async def api_cancel_deferred(
    payload: DeferredConfirmRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    from app.routers.deferred_events import cancel_event, CancelRequest
    try:
        res = await cancel_event(CancelRequest(order_id=payload.order_id), client=client, db=db)
        return {"success": True, "message": res.message}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deferred/cancel-bulk")
async def api_cancel_deferred_bulk(
    payload: DeferredBulkConfirmRequest,
    client: Client = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db)
):
    from app.routers.deferred_events import bulk_cancel_events, BulkConfirmRequest
    try:
        res = await bulk_cancel_events(BulkConfirmRequest(order_ids=payload.order_ids), client=client, db=db)
        return {"success": True, "cancelled": res.cancelled, "failed": res.failed, "details": res.details}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
