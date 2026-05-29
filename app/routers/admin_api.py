import os
import secrets
import logging
import hmac
import time
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sql_delete, select, func
from pydantic import BaseModel

from app.database import get_db
from app.models.client import Client
from app.models.event_dedup import EventDedup
from app.models.event_log import EventLog
from app.models.event_outbox import EventOutbox
from app.models.failed_event import FailedEvent
from app.models.pending_event import PendingEvent
from app.models.usage_counter import UsageCounter
from app.security import encrypt_token
from app.services.webhook_service import _webhook_url_allowed
from app.dependencies import clear_client_cache
from app.utils.display import normalize_domain_input, display_domain_url, mask_secret
from app.routers.admin_views import log_admin_action
from app.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter()

class AdminClientCreate(BaseModel):
    name: str
    pixel_id: str
    access_token: str
    test_event_code: str | None = None
    domain: str | None = None
    tiktok_pixel_id: str | None = None
    tiktok_access_token: str | None = None
    tiktok_test_event_code: str | None = None
    ga4_measurement_id: str | None = None
    ga4_api_secret: str | None = None
    enable_facebook: bool = True
    enable_tiktok: bool = True
    enable_ga4: bool = True
    deferred_purchase: bool = False
    webhook_url: str | None = None

class AdminClientUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    monthly_limit: int | None = None
    is_active: bool | None = None
    enable_facebook: bool | None = None
    enable_tiktok: bool | None = None
    enable_ga4: bool | None = None
    deferred_purchase: bool | None = None
    webhook_url: str | None = None
    test_event_code: str | None = None
    tiktok_test_event_code: str | None = None

import jwt as pyjwt

def create_jwt(payload: dict, secret: str) -> str:
    """PyJWT দিয়ে HS256 JWT token তৈরি করো।"""
    return pyjwt.encode(payload, secret, algorithm="HS256")

def decode_jwt(token: str, secret: str) -> dict:
    """PyJWT দিয়ে JWT token decode ও verify করো।"""
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except pyjwt.InvalidTokenError as e:
        raise ValueError(f"Token decoding failed: {e}")

def verify_admin_api_key(
    authorization: str = Header(None, alias="Authorization"),
    x_admin_api_key: str = Header(None, alias="X-Admin-API-Key"),
) -> str:
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin API key is not configured")
    
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            payload = decode_jwt(token, admin_key)
            if payload.get("sub") == "admin":
                return "admin-api"
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")
            
    if x_admin_api_key and hmac.compare_digest(x_admin_api_key, admin_key):
        return "admin-api"
        
    raise HTTPException(status_code=403, detail="Admin access required")

def client_to_api_dict(client: Client, event_total: int = 0, last_event_at=None, mask_keys: bool = False) -> dict:
    api_key = mask_secret(client.api_key) if mask_keys else client.api_key
    public_key = getattr(client, "public_key", None)
    if public_key and mask_keys:
        public_key = mask_secret(public_key)
    portal_key = getattr(client, "portal_key", None)
    if portal_key and mask_keys:
        portal_key = mask_secret(portal_key)

    return {
        "id": client.id,
        "name": client.name,
        "domain": client.domain,
        "display_domain": display_domain_url(client.domain),
        "is_active": bool(client.is_active),
        "api_key": api_key,
        "public_key": public_key,
        "portal_key": portal_key,
        "pixel_id": client.pixel_id,
        "test_event_code": client.test_event_code,
        "monthly_limit": getattr(client, "monthly_limit", None),
        "rate_limit": client.rate_limit,
        "daily_quota": client.daily_quota,
        "enable_facebook": getattr(client, "enable_facebook", True),
        "enable_tiktok": getattr(client, "enable_tiktok", True),
        "enable_ga4": getattr(client, "enable_ga4", True),
        "deferred_purchase": getattr(client, "deferred_purchase", False),
        "webhook_url": getattr(client, "webhook_url", None),
        "tiktok_pixel_id": getattr(client, "tiktok_pixel_id", None),
        "ga4_measurement_id": getattr(client, "ga4_measurement_id", None),
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "event_total": int(event_total or 0),
        "last_event_at": last_event_at.isoformat() if last_event_at else None,
    }

async def validate_webhook_url_or_400(webhook_url: str | None) -> str | None:
    clean_webhook_url = webhook_url.strip() if webhook_url and webhook_url.strip() else None
    if not clean_webhook_url:
        return None
    parsed_webhook = urlparse(clean_webhook_url)
    if parsed_webhook.scheme not in ("https", "http") or not parsed_webhook.netloc:
        raise HTTPException(status_code=400, detail="Webhook URL must be a valid http(s) URL.")
    if not await _webhook_url_allowed(clean_webhook_url):
        raise HTTPException(status_code=400, detail="Webhook URL is not allowed.")
    return clean_webhook_url

@router.get("/admin/api/summary")
async def admin_api_summary(
    _: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    clients_r = await db.execute(select(Client))
    clients = clients_r.scalars().all()
    events_r = await db.execute(select(func.coalesce(func.sum(EventLog.event_count), 0)))
    total_events = int(events_r.scalar() or 0)
    failed_r = await db.execute(
        select(func.coalesce(func.sum(EventLog.event_count), 0)).where(EventLog.status == "failed")
    )
    failed_events = int(failed_r.scalar() or 0)
    return {
        "status": "success",
        "total_clients": len(clients),
        "active_clients": sum(1 for c in clients if c.is_active),
        "inactive_clients": sum(1 for c in clients if not c.is_active),
        "total_events": total_events,
        "failed_events": failed_events,
    }

@router.get("/admin/api/clients")
async def admin_api_clients(
    _: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(
            Client,
            func.coalesce(func.sum(EventLog.event_count), 0).label("event_total"),
            func.max(EventLog.created_at).label("last_event_at"),
        )
        .outerjoin(EventLog, EventLog.client_id == Client.id)
        .group_by(Client.id)
        .order_by(Client.created_at.desc())
    )
    return {
        "status": "success",
        "clients": [client_to_api_dict(client, event_total, last_event_at, mask_keys=True) for client, event_total, last_event_at in rows],
    }

@router.post("/admin/api/clients")
@limiter.limit("10/minute")
async def admin_api_create_client(
    payload: AdminClientCreate,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    name = payload.name.strip()
    pixel_id = payload.pixel_id.strip()
    access_token = payload.access_token.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Client name must be 1-100 characters.")
    if not pixel_id.isdigit():
        raise HTTPException(status_code=400, detail="Pixel ID must be numeric.")
    if len(access_token) < 10:
        raise HTTPException(status_code=400, detail="Access token must be at least 10 characters.")

    client = Client(
        name=name,
        pixel_id=pixel_id,
        access_token=encrypt_token(access_token),
        test_event_code=payload.test_event_code.strip() if payload.test_event_code else None,
        domain=normalize_domain_input(payload.domain),
        api_key=secrets.token_urlsafe(32),
        public_key=secrets.token_urlsafe(24),
        portal_key=secrets.token_urlsafe(24),
        enable_facebook=payload.enable_facebook,
        enable_tiktok=payload.enable_tiktok,
        enable_ga4=payload.enable_ga4,
        tiktok_pixel_id=payload.tiktok_pixel_id.strip() if payload.tiktok_pixel_id else None,
        tiktok_access_token=encrypt_token(payload.tiktok_access_token.strip()) if payload.tiktok_access_token else None,
        tiktok_test_event_code=payload.tiktok_test_event_code.strip() if payload.tiktok_test_event_code else None,
        ga4_measurement_id=payload.ga4_measurement_id.strip() if payload.ga4_measurement_id else None,
        ga4_api_secret=encrypt_token(payload.ga4_api_secret.strip()) if payload.ga4_api_secret else None,
        deferred_purchase=payload.deferred_purchase,
        webhook_url=await validate_webhook_url_or_400(payload.webhook_url),
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    await log_admin_action(db, request, actor, "client.api_added", client.id, f"Client {name} added from admin frontend")
    await db.commit()
    return {"status": "success", "client": client_to_api_dict(client)}

@router.patch("/admin/api/clients/{client_id}")
@limiter.limit("20/minute")
async def admin_api_update_client(
    client_id: int,
    payload: AdminClientUpdate,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    old_api_key = client.api_key
    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name or len(clean_name) > 100:
            raise HTTPException(status_code=400, detail="Client name must be 1-100 characters.")
        client.name = clean_name
    if payload.domain is not None:
        client.domain = normalize_domain_input(payload.domain)
    if payload.monthly_limit is not None:
        if payload.monthly_limit < 0:
            raise HTTPException(status_code=400, detail="Monthly limit cannot be negative.")
        client.monthly_limit = payload.monthly_limit
    if payload.is_active is not None:
        client.is_active = payload.is_active
    for field in ("enable_facebook", "enable_tiktok", "enable_ga4", "deferred_purchase"):
        value = getattr(payload, field)
        if value is not None:
            setattr(client, field, value)
    if payload.webhook_url is not None:
        client.webhook_url = await validate_webhook_url_or_400(payload.webhook_url)
    if payload.test_event_code is not None:
        client.test_event_code = payload.test_event_code.strip() or None
    if payload.tiktok_test_event_code is not None:
        client.tiktok_test_event_code = payload.tiktok_test_event_code.strip() or None

    await db.commit()
    await db.refresh(client)
    clear_client_cache(old_api_key)
    await log_admin_action(db, request, actor, "client.api_updated", client.id, f"Client {client.name} updated from admin frontend")
    await db.commit()
    return {"status": "success", "client": client_to_api_dict(client)}

@router.get("/admin/api/clients/{client_id}")
async def admin_api_get_client(
    client_id: int,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    data = client_to_api_dict(client)
    data["access_token"] = mask_secret(client.access_token) if client.access_token else ""
    data["portal_key"] = client.portal_key
    data["public_key"] = getattr(client, "public_key", None)
    return {"status": "success", "client": data}

@router.post("/admin/api/clients/{client_id}/keys/rotate")
@limiter.limit("10/minute")
async def admin_api_rotate_key(
    client_id: int,
    request: Request,
    payload: dict,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    key_type = payload.get("key_type")
    if key_type not in ["api_key", "portal_key", "public_key"]:
        raise HTTPException(status_code=400, detail="Invalid key type")

    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    old_key = client.api_key
    if key_type == "api_key":
        client.api_key = secrets.token_urlsafe(32)
        clear_client_cache(old_key)
    elif key_type == "portal_key":
        client.portal_key = secrets.token_urlsafe(16)
    elif key_type == "public_key" and hasattr(client, "public_key"):
        client.public_key = secrets.token_hex(16)

    await log_admin_action(db, request, actor, f"client.{key_type}_rotated", client.id, f"{key_type} rotated via admin API")
    await db.commit()
    await db.refresh(client)
    return {"status": "success", "key_type": key_type, "new_value": getattr(client, key_type)}

@router.delete("/admin/api/clients/{client_id}")
@limiter.limit("5/minute")
async def admin_api_delete_client(
    client_id: int,
    request: Request,
    actor: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client_name = client.name
    client_api_key = client.api_key

    await db.execute(sql_delete(EventOutbox).where(EventOutbox.client_id == client_id))
    await db.execute(sql_delete(FailedEvent).where(FailedEvent.client_id == client_id))
    await db.execute(sql_delete(PendingEvent).where(PendingEvent.client_id == client_id))
    await db.execute(sql_delete(EventDedup).where(EventDedup.client_id == client_id))
    await db.execute(sql_delete(UsageCounter).where(UsageCounter.client_id == client_id))
    await db.execute(sql_delete(EventLog).where(EventLog.client_id == client_id))

    # Delete client sessions and users to avoid foreign key constraint violations
    from app.models.client_session import ClientSession
    from app.models.client_user import ClientUser
    await db.execute(sql_delete(ClientSession).where(ClientSession.client_id == client_id))
    await db.execute(sql_delete(ClientUser).where(ClientUser.client_id == client_id))

    await db.delete(client)
    clear_client_cache(client_api_key)

    await log_admin_action(db, request, actor, "client.deleted", client_id, f"Client {client_name} deleted via API")
    await db.commit()
    return {"status": "success", "message": f"Client {client_name} deleted"}

class AdminLoginRequest(BaseModel):
    username: str
    password: str

@router.post("/admin/api/login")
@limiter.limit("5/minute")
async def admin_api_login(request: Request, payload: AdminLoginRequest):
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD")
    admin_key = os.getenv("ADMIN_API_KEY")

    if not admin_pass or not admin_key:
        raise HTTPException(
            status_code=500,
            detail="Admin authentication is not configured on the server."
        )

    if not hmac.compare_digest(payload.username, admin_user) or not hmac.compare_digest(payload.password, admin_pass):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password"
        )

    token_payload = {
        "sub": "admin",
        "exp": int(time.time()) + 24 * 3600
    }
    jwt_token = create_jwt(token_payload, admin_key)

    return {"status": "success", "admin_api_key": jwt_token, "token": jwt_token}

def escape_sql_wildcards(search_term: str) -> str:
    if not search_term:
        return ""
    return search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

@router.get("/admin/api/events")
async def admin_api_events(
    _: str = Depends(verify_admin_api_key),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
    client_id: int | None = None,
    status: str | None = None,
    platform: str | None = None,
    search: str | None = None,
):
    from datetime import datetime, timezone
    from sqlalchemy import desc

    query = select(EventLog).order_by(desc(EventLog.created_at))
    count_query = select(func.count(EventLog.id))

    if client_id:
        query = query.where(EventLog.client_id == client_id)
        count_query = count_query.where(EventLog.client_id == client_id)

    if status:
        status_list = status.split(",")
        db_statuses = [s.lower() for s in status_list]
        query = query.where(EventLog.status.in_(db_statuses))
        count_query = count_query.where(EventLog.status.in_(db_statuses))

    if platform:
        if platform == "GA4":
            query = query.where(EventLog.event_name.like("GA4:%"))
            count_query = count_query.where(EventLog.event_name.like("GA4:%"))
        elif platform == "TikTok Events API":
            query = query.where(EventLog.event_name.like("TikTok:%"))
            count_query = count_query.where(EventLog.event_name.like("TikTok:%"))
        elif platform == "Webhook":
            query = query.where(EventLog.event_name.like("Webhook:%"))
            count_query = count_query.where(EventLog.event_name.like("Webhook:%"))
        elif platform == "Meta CAPI":
            query = query.where(
                (EventLog.event_name.like("Facebook:%")) | (~EventLog.event_name.contains(":"))
            )
            count_query = count_query.where(
                (EventLog.event_name.like("Facebook:%")) | (~EventLog.event_name.contains(":"))
            )

    if search:
        escaped_search = escape_sql_wildcards(search)
        query = query.where(
            EventLog.event_name.ilike(f"%{escaped_search}%", escape="\\") |
            EventLog.ip_address.ilike(f"%{escaped_search}%", escape="\\") |
            EventLog.error_message.ilike(f"%{escaped_search}%", escape="\\")
        )
        count_query = count_query.where(
            EventLog.event_name.ilike(f"%{escaped_search}%", escape="\\") |
            EventLog.ip_address.ilike(f"%{escaped_search}%", escape="\\") |
            EventLog.error_message.ilike(f"%{escaped_search}%", escape="\\")
        )

    result = await db.execute(query.offset(offset).limit(limit))
    logs = result.scalars().all()

    count_r = await db.execute(count_query)
    total_count = count_r.scalar() or 0

    clients_r = await db.execute(select(Client))
    clients = clients_r.scalars().all()
    client_map = {c.id: c.name for c in clients}

    events_list = []
    for log in logs:
        raw_event_name = log.event_name
        log_platform = "Meta CAPI"
        display_event_name = raw_event_name

        if ":" in raw_event_name:
            parts = raw_event_name.split(":", 1)
            channel = parts[0]
            display_event_name = parts[1]
            if channel.lower() == "tiktok":
                log_platform = "TikTok Events API"
            elif channel.lower() == "ga4":
                log_platform = "GA4"
            elif channel.lower() in ("facebook", "capi", "meta"):
                log_platform = "Meta CAPI"
            elif channel.lower() == "webhook":
                log_platform = "Webhook"

        events_list.append({
            "id": f"evt_{log.id}",
            "client_id": log.client_id,
            "client_name": client_map.get(log.client_id, f"Client #{log.client_id}"),
            "timestamp": log.created_at.isoformat() if log.created_at else datetime.now(timezone.utc).isoformat(),
            "name": display_event_name,
            "platform": log_platform,
            "status": "Success" if log.status == "success" else "Failed",
            "httpCode": 200 if log.status == "success" else 400,
            "deduplicationKey": log.event_id or f"did_{log.id}",
            "payload": {
                "event_name": display_event_name,
                "event_time": int(log.created_at.timestamp()) if log.created_at else int(datetime.now().timestamp()),
                "user_data": {
                    "client_ip_address": log.ip_address or "127.0.0.1",
                    "client_user_agent": "Mozilla/5.0"
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
            "latencyMs": None
        })

    return {
        "status": "success",
        "events": events_list,
        "totalCount": total_count
    }
