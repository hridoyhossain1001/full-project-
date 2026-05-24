import os
import secrets
import logging
import hmac
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
from app.utils.display import normalize_domain_input, display_domain_url
from app.routers.admin_views import log_admin_action

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

def verify_admin_api_key(x_admin_api_key: str = Header("", alias="X-Admin-API-Key")) -> str:
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin API key is not configured")
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, admin_key):
        raise HTTPException(status_code=403, detail="Admin access required")
    return "admin-api"

def client_to_api_dict(client: Client, event_total: int = 0, last_event_at=None) -> dict:
    return {
        "id": client.id,
        "name": client.name,
        "domain": client.domain,
        "display_domain": display_domain_url(client.domain),
        "is_active": bool(client.is_active),
        "api_key": client.api_key,
        "public_key": getattr(client, "public_key", None),
        "portal_key": getattr(client, "portal_key", None),
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

def validate_webhook_url_or_400(webhook_url: str | None) -> str | None:
    clean_webhook_url = webhook_url.strip() if webhook_url and webhook_url.strip() else None
    if not clean_webhook_url:
        return None
    parsed_webhook = urlparse(clean_webhook_url)
    if parsed_webhook.scheme not in ("https", "http") or not parsed_webhook.netloc:
        raise HTTPException(status_code=400, detail="Webhook URL must be a valid http(s) URL.")
    if not _webhook_url_allowed(clean_webhook_url):
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
        "clients": [client_to_api_dict(client, event_total, last_event_at) for client, event_total, last_event_at in rows],
    }

@router.post("/admin/api/clients")
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
        webhook_url=validate_webhook_url_or_400(payload.webhook_url),
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    await log_admin_action(db, request, actor, "client.api_added", client.id, f"Client {name} added from admin frontend")
    await db.commit()
    return {"status": "success", "client": client_to_api_dict(client)}

@router.patch("/admin/api/clients/{client_id}")
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
        client.webhook_url = validate_webhook_url_or_400(payload.webhook_url)
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
    data["access_token"] = client.access_token
    data["portal_key"] = client.portal_key
    data["public_key"] = getattr(client, "public_key", None)
    return {"status": "success", "client": data}

@router.post("/admin/api/clients/{client_id}/keys/rotate")
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
    await db.delete(client)
    clear_client_cache(client_api_key)

    await log_admin_action(db, request, actor, "client.deleted", client_id, f"Client {client_name} deleted via API")
    await db.commit()
    return {"status": "success", "message": f"Client {client_name} deleted"}
