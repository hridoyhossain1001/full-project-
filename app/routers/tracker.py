"""
Tracker Router — Custom JavaScript Pixel সার্ভ ও ইভেন্ট কালেকশন।

Endpoints:
  GET  /t.js?key=API_KEY  → ডায়নামিক JS ট্র্যাকার সার্ভ করে
  POST /c?key=API_KEY     → ব্রাউজার থেকে ইভেন্ট রিসিভ করে ও Facebook-এ পাঠায়

এন্ডপয়েন্টের নাম ছোট ও জেনেরিক রাখা হয়েছে যাতে অ্যাড ব্লকার detect করতে না পারে।
"""

import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from user_agents import parse as parse_ua

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Query
from fastapi.responses import Response, JSONResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.dependencies import get_current_client, CachedClient, _client_cache, _snapshot, CACHE_TTL
from app.models.client import Client
from app.models.event_dedup import EventDedup
from app.models.event_log import EventLog
from app.schemas.event import EventData, UserData, CustomData
from app.services.bot_detector import is_bot
from app.services.capi_service import send_to_facebook
from app.services.tiktok_service import send_to_tiktok
from app.services.geoip_service import get_location_data
from app.services.ga4_service import send_to_ga4
from app.services.retry_service import save_failed_event
from app.services.tracker_sdk import generate_tracker_js
from app.services.usage_service import check_usage_limits_db, increment_usage_counters_db

from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Helper: API Key থেকে Client লোড (Query param version) ──────────────────
async def _get_client_by_key(api_key: str, db: AsyncSession) -> CachedClient:
    """
    Query parameter থেকে আসা API Key দিয়ে ক্লায়েন্ট খোঁজে।
    In-memory cache ব্যবহার করে — dependencies.py-এর সাথে cache শেয়ার করে।
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key প্রয়োজন।")

    # Cache check
    now = time.time()
    if api_key in _client_cache:
        cached, cached_at = _client_cache[api_key]
        if now - cached_at < CACHE_TTL:
            if cached.is_active:
                return cached
            raise HTTPException(status_code=401, detail="Inactive API Key।")

    # DB lookup
    result = await db.execute(
        select(Client).where(Client.api_key == api_key, Client.is_active == True)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid API Key।")

    cached = _snapshot(client)
    _client_cache[api_key] = (cached, now)
    return cached


# ═══════════════════════════════════════════════════════════════════════════════
# GET /t.js — Dynamic JavaScript Tracker সার্ভ করা
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/t.js", include_in_schema=False)
async def serve_tracker_js(
    request: Request,
    key: str = Query(..., description="Client API Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    ক্লায়েন্টের API Key ভেরিফাই করে ডায়নামিক JavaScript ট্র্যাকার সার্ভ করে।
    Response-এ proper caching headers সেট করা হয়।
    """
    # Validate API Key
    client = await _get_client_by_key(key, db)

    # Gateway origin detect করো (ক্লায়েন্টের custom domain বা Heroku URL)
    # Request যেই host-এ আসছে সেটাই ব্যবহার করবে
    scheme = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("host", "localhost")
    gateway_origin = f"{scheme}://{host}"

    # Generate JS
    js_code = generate_tracker_js(api_key=key, gateway_origin=gateway_origin)

    return Response(
        content=js_code,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600",  # 1 ঘণ্টা ব্রাউজার cache
            "X-Content-Type-Options": "nosniff",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POST /c — Collect Endpoint (ব্রাউজার থেকে ইভেন্ট রিসিভ)
# ═══════════════════════════════════════════════════════════════════════════════

async def _save_success_logs(client_id: int, events_data: list, fb_result: dict | None, client_ip: str | None):
    """Background task: সফল ইভেন্টের লগ সেভ করে।"""
    try:
        async with AsyncSessionLocal() as db:
            log_entries = [
                EventLog(
                    client_id=client_id,
                    event_name=event.get("event_name", "unknown"),
                    event_id=event.get("event_id"),
                    event_count=1,
                    status="success",
                    fb_response=json.dumps(fb_result) if fb_result else None,
                    ip_address=client_ip,
                    emq_score=event.get("emq_score"),
                )
                for event in events_data
            ]
            db.add_all(log_entries)
            await db.commit()
    except Exception as e:
        logger.error(f"Tracker success log error: {e}")


async def _save_failure_logs(client_id: int, events_data: list, error_msg: str, client_ip: str | None):
    """Background task: ফেইল ইভেন্টের লগ ও retry queue সেভ করে।"""
    try:
        async with AsyncSessionLocal() as db:
            event_names = ", ".join(sorted({e.get("event_name", "unknown") for e in events_data}))
            log_entry = EventLog(
                client_id=client_id,
                event_name=event_names,
                event_count=len(events_data),
                status="failed",
                error_message=error_msg[:500],
                ip_address=client_ip,
            )
            db.add(log_entry)
            await db.commit()
            await save_failed_event(db, client_id, events_data, error_msg)
    except Exception as e:
        logger.error(f"Tracker failure log error: {e}")


@router.post("/c", include_in_schema=False)
async def collect_event(
    request: Request,
    background_tasks: BackgroundTasks,
    key: str = Query(..., description="Client API Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    ব্রাউজারের ট্র্যাকার JS থেকে ইভেন্ট রিসিভ করে।
    Bot detection করে, dedup চেক করে, তারপর Facebook CAPI-তে ফরওয়ার্ড করে।
    """
    # ─── Parse body (Beacon API sends as blob) ────────────────────────
    try:
        body = await request.json()
    except Exception:
        # Beacon API sometimes sends with wrong content-type
        raw = await request.body()
        try:
            body = json.loads(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not body or not body.get("data"):
        raise HTTPException(status_code=400, detail="Empty event data")

    # ─── Validate API Key ─────────────────────────────────────────────
    client = await _get_client_by_key(key, db)

    # ─── Real IP Detection ────────────────────────────────────────────
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)

    # ─── Bot Detection ────────────────────────────────────────────────
    user_agent = request.headers.get("user-agent", "")
    if is_bot(user_agent):
        logger.info(f"[{client.name}] 🤖 Bot event dropped from tracker")
        # Return 200 to not leak bot detection to caller
        return {"status": "ok", "events_received": 0, "message": "processed"}

    # ─── Domain Whitelisting ──────────────────────────────────────────
    if client.domain:
        origin = request.headers.get("origin", "") or ""
        referer = request.headers.get("referer", "") or ""
        allowed = client.domain.lower().strip()
        origin_host = (urlparse(origin).hostname or "").lower()
        referer_host = (urlparse(referer).hostname or "").lower()

        def _domain_ok(host: str) -> bool:
            return host == allowed or host.endswith("." + allowed)

        if not (_domain_ok(origin_host) or _domain_ok(referer_host)):
            logger.warning(f"[{client.name}] Tracker domain mismatch: {origin_host} / {referer_host}")
            raise HTTPException(status_code=403, detail="Unauthorized domain.")

    # ─── Parse Events ─────────────────────────────────────────────────
    raw_events = body.get("data", [])
    if len(raw_events) > 50:
        raw_events = raw_events[:50]  # Tracker থেকে max 50 events

    parsed_events = []
    for raw in raw_events:
        try:
            # user_data build
            ud_raw = raw.get("user_data", {})
            # Inject real IP if missing
            if not ud_raw.get("client_ip_address") or ud_raw.get("client_ip_address") in ("8.8.8.8", "127.0.0.1", ""):
                ud_raw["client_ip_address"] = client_ip
            if not ud_raw.get("client_user_agent"):
                ud_raw["client_user_agent"] = user_agent

            # ─── GeoIP Enrichment ──────────────────────────────────────────
            if ud_raw.get("client_ip_address"):
                loc_data = get_location_data(ud_raw["client_ip_address"])
                if loc_data:
                    if loc_data.get("ct") and not ud_raw.get("ct"):
                        ud_raw["ct"] = loc_data["ct"]
                    if loc_data.get("st") and not ud_raw.get("st"):
                        ud_raw["st"] = loc_data["st"]
                    if loc_data.get("country") and not ud_raw.get("country"):
                        ud_raw["country"] = loc_data["country"]
                    if loc_data.get("zp") and not ud_raw.get("zp"):
                        ud_raw["zp"] = loc_data["zp"]

            # ─── Event Match Quality (EMQ) ─────────────────────────────────
            emq = 0.0
            if ud_raw.get("em"): emq += 3.0
            if ud_raw.get("ph"): emq += 3.0
            if ud_raw.get("fbp") or ud_raw.get("fbc"): emq += 1.0
            if ud_raw.get("client_ip_address") and ud_raw.get("client_user_agent"): emq += 1.0
            other_pii = sum(1 for k in ["fn", "ln", "ct", "st", "zp", "country"] if ud_raw.get(k))
            if other_pii >= 2: emq += 2.0
            elif other_pii == 1: emq += 1.0
            emq = min(10.0, emq)

            user_data = UserData(**ud_raw)

            # custom_data (optional)
            custom_data_dict = raw.get("custom_data", {})
            if custom_data_dict is None:
                custom_data_dict = {}

            # ─── User-Agent Parsing ────────────────────────────────────────
            if ud_raw.get("client_user_agent"):
                ua = parse_ua(ud_raw["client_user_agent"])
                custom_data_dict["device_type"] = "Mobile" if ua.is_mobile else "Tablet" if ua.is_tablet else "PC"
                custom_data_dict["os_name"] = ua.os.family
                custom_data_dict["browser_name"] = ua.browser.family

            # ─── UTM Parameter Extraction ──────────────────────────────────
            event_url = raw.get("event_source_url", "")
            if event_url:
                parsed_url = urlparse(event_url)
                qs = parse_qs(parsed_url.query)
                for utm_key in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]:
                    if utm_key in qs:
                        custom_data_dict[utm_key] = qs[utm_key][0]

            custom_data = CustomData(**custom_data_dict)

            event = EventData(
                event_name=raw.get("event_name", "PageView"),
                event_time=raw.get("event_time", int(datetime.now(timezone.utc).timestamp())),
                event_id=raw.get("event_id"),
                event_source_url=raw.get("event_source_url"),
                action_source=raw.get("action_source", "website"),
                user_data=user_data,
                custom_data=custom_data,
                emq_score=emq,
            )
            parsed_events.append(event)
        except Exception as e:
            logger.warning(f"[{client.name}] Tracker event parse error: {e}")
            continue

    if not parsed_events:
        return {"status": "ok", "events_received": 0, "message": "no valid events"}

    # ─── Usage Limit Check ────────────────────────────────────────────
    try:
        await check_usage_limits_db(db, client, len(parsed_events))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[{client.name}] Usage check error (non-fatal): {e}")

    # ─── Dedup ────────────────────────────────────────────────────────
    unique_events = []
    candidate_ids = []
    seen_ids = set()

    for event in parsed_events:
        if not event.event_id or event.event_id in seen_ids:
            if not event.event_id:
                unique_events.append(event)
            continue
        seen_ids.add(event.event_id)
        candidate_ids.append(event.event_id)

    if candidate_ids:
        try:
            rows = [{"client_id": client.id, "event_id": eid} for eid in candidate_ids]
            stmt = (
                pg_insert(EventDedup)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["client_id", "event_id"])
                .returning(EventDedup.event_id)
            )
            result = await db.execute(stmt)
            reserved_ids = set(result.scalars().all())
            await db.commit()

            for event in parsed_events:
                if event.event_id and event.event_id in reserved_ids:
                    unique_events.append(event)
        except Exception:
            await db.rollback()
            # On dedup failure, send all events (better than losing data)
            unique_events = parsed_events

    if not unique_events:
        return {"status": "ok", "events_received": 0, "message": "deduplicated"}

    # ─── Send to Facebook ─────────────────────────────────────────────
    events_as_dicts = [event.model_dump(exclude_none=True) for event in unique_events]

    try:
        result = await send_to_facebook(client, unique_events)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{client.name}] Tracker → FB Error: {error_msg}")
        background_tasks.add_task(_save_failure_logs, client.id, events_as_dicts, error_msg, client_ip)
        # Return 200 to browser (don't expose server errors to frontend)
        return {"status": "ok", "events_received": len(unique_events), "message": "queued for retry"}

    # ─── Increment Usage ──────────────────────────────────────────────
    try:
        async with AsyncSessionLocal() as usage_db:
            await increment_usage_counters_db(usage_db, client, len(unique_events))
    except Exception as e:
        logger.warning(f"[{client.name}] Usage counter error (non-fatal): {e}")

    # ─── Success Logs ───────────────────────────────────────────────────────
    background_tasks.add_task(_save_success_logs, client.id, events_as_dicts, result, client_ip)

    # ─── TikTok CAPI (parallel, non-blocking) ─────────────────────────
    if client.tiktok_pixel_id and client.tiktok_access_token:
        background_tasks.add_task(send_to_tiktok, client, unique_events)

    # ─── GA4 Server-Side (parallel, non-blocking) ─────────────────────
    if client.ga4_measurement_id and client.ga4_api_secret:
        ga4_events = [evt.model_dump(exclude_none=True) for evt in unique_events]
        background_tasks.add_task(
            send_to_ga4,
            events=ga4_events,
            measurement_id=client.ga4_measurement_id,
            api_secret=client.ga4_api_secret,
            cookies=request.cookies,
            ip_address=client_ip,
            user_agent=user_agent
        )

    # ─── Cookie Life Extension (Safari ITP Bypass) ────────────────────
    # Server-side Set-Cookie ইস্যু করে _fbp ও _fbc কুকির মেয়াদ ৬ মাস পর্যন্ত বাড়ানো হয়।
    # Safari ITP ব্রাউজারে JavaScript দিয়ে সেট করা কুকি ১-৭ দিনে expire হয়, কিন্তু
    # সার্ভার (HTTP header) থেকে Set-Cookie করলে ITP bypass হয়!
    response_data = {"status": "ok", "events_received": len(unique_events), "message": "sent"}
    resp = JSONResponse(content=response_data)

    # ব্রাউজার থেকে পাঠানো _fbp/_fbc ভ্যালু খোঁজো (body-তে থাকতে পারে)
    first_event = body.get("data", [{}])[0] if body.get("data") else {}
    ud = first_event.get("user_data", {})
    fbp_val = ud.get("fbp", "")
    fbc_val = ud.get("fbc", "")

    cookie_max_age = 180 * 24 * 60 * 60  # 180 দিন (৬ মাস)

    if fbp_val:
        resp.set_cookie(
            key="_fbp",
            value=fbp_val,
            max_age=cookie_max_age,
            httponly=False,   # JS থেকেও পড়তে হবে
            secure=True,
            samesite="lax",
            path="/",
        )
    if fbc_val:
        resp.set_cookie(
            key="_fbc",
            value=fbc_val,
            max_age=cookie_max_age,
            httponly=False,
            secure=True,
            samesite="lax",
            path="/",
        )

    return resp
