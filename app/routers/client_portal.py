from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
import datetime
import secrets
from typing import Optional

from app.database import get_db
from app.models.client import Client
from app.models.event_log import EventLog
from app.models.pending_event import PendingEvent
from app.utils.display import display_domain_url, mask_secret
from app.security import encrypt_token, decrypt_token
from app.limiter import limiter
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["mask_secret"] = mask_secret
templates.env.globals["display_domain_url"] = display_domain_url

router = APIRouter(tags=["Client Portal"])


def get_client_from_cookie(request: Request) -> Optional[str]:
    """Cookie থেকে encrypted session token পড়ে decrypt করে API key রিটার্ন করে।"""
    encrypted = request.cookies.get("client_session")
    if not encrypted:
        return None
    try:
        return decrypt_token(encrypted, allow_legacy_plaintext=False)
    except Exception:
        return None


async def get_client_from_portal_session(request: Request, db: AsyncSession) -> Optional[Client]:
    session_value = get_client_from_cookie(request)
    if not session_value:
        return None

    if session_value.startswith("client:"):
        try:
            _, client_id, session_secret = session_value.split(":", 2)
            result = await db.execute(select(Client).where(Client.id == int(client_id)))
            client = result.scalar_one_or_none()
            expected_secret = getattr(client, "portal_key", None) if client else None
            if client and expected_secret and secrets.compare_digest(session_secret, expected_secret):
                return client
            return None
        except (TypeError, ValueError):
            return None

    # Backward compatibility for old cookies that stored the API key directly.
    result = await db.execute(select(Client).where(Client.api_key == session_value))
    return result.scalar_one_or_none()


@router.get("/client", response_class=HTMLResponse, include_in_schema=False)
async def client_login_page(request: Request):
    api_key = get_client_from_cookie(request)
    if api_key:
        return RedirectResponse(url="/client/dashboard", status_code=303)

    return templates.TemplateResponse(
        request,
        "client_portal/login.html",
        {"title": "Client Login"}
    )


@router.post("/client/login", include_in_schema=False)
@limiter.limit("5/minute")
async def client_login(request: Request, response: Response, api_key: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Client).where(or_(Client.portal_key == api_key, Client.api_key == api_key))
    )
    client = result.scalar_one_or_none()
    portal_key = getattr(client, "portal_key", None) if client else None
    portal_key_ok = bool(portal_key) and secrets.compare_digest(portal_key, api_key)
    legacy_api_key_ok = bool(client and not portal_key) and secrets.compare_digest(client.api_key, api_key)

    if not client or not client.is_active or not (portal_key_ok or legacy_api_key_ok):
        return templates.TemplateResponse(
            request,
            "client_portal/login_failed.html",
            {"title": "Login Failed"},
            status_code=401
        )

    redirect = RedirectResponse(url="/client/dashboard", status_code=303)
    redirect.set_cookie(
        key="client_session",
        value=encrypt_token(f"client:{client.id}:{getattr(client, 'portal_key', None) or client.api_key}"),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )
    return redirect


@router.get("/client/logout", include_in_schema=False)
async def client_logout():
    redirect = RedirectResponse(url="/client", status_code=303)
    redirect.delete_cookie("client_session")
    return redirect


@router.get("/client/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def client_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    client = await get_client_from_portal_session(request, db)
    if not client:
        return RedirectResponse(url="/client", status_code=303)

    if not client.is_active:
        redirect = RedirectResponse(url="/client", status_code=303)
        redirect.delete_cookie("client_session")
        return redirect

    # Load and serve the React compiled index.html
    import os
    index_path = os.path.join(os.path.dirname(__file__), "..", "static", "client-portal", "index.html")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Dynamically replace relative assets paths with absolute paths served under our static route
        content = content.replace("./assets/", "/static/client-portal/assets/")
        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Failed to serve SPA index.html: {e}")
        raise HTTPException(status_code=500, detail="Client portal SPA index file not found. Run vite compile build.")


@router.post("/client/settings/update", include_in_schema=False)
@limiter.limit("10/minute")
async def client_settings_update(
    request: Request,
    pixel_id: str = Form(""),
    access_token: str = Form(""),
    test_event_code: str = Form(""),
    tiktok_pixel_id: str = Form(""),
    tiktok_access_token: str = Form(""),
    tiktok_test_event_code: str = Form(""),
    ga4_measurement_id: str = Form(""),
    ga4_api_secret: str = Form(""),
    enable_facebook: str = Form(None),
    enable_tiktok: str = Form(None),
    enable_ga4: str = Form(None),
    deferred_purchase: str = Form(None),
    domain: str = Form(None),
    auto_confirm_days: int = Form(0),
    auto_confirm_status: str = Form("completed"),
    db: AsyncSession = Depends(get_db),
):
    client = await get_client_from_portal_session(request, db)
    if not client or not client.is_active:
        return RedirectResponse(url="/client", status_code=303)

    # ─── Validate Pixel ID if provided ─────────────────────────────────────
    if pixel_id and pixel_id.strip():
        if not pixel_id.strip().isdigit():
            from urllib.parse import urlencode
            q = urlencode({"settings_msg": "Pixel ID শুধু সংখ্যা হতে হবে।", "settings_type": "error"})
            return RedirectResponse(url=f"/client/dashboard?{q}#tab-settings", status_code=303)
        client.pixel_id = pixel_id.strip()

    # ─── Update non-sensitive fields always ─────────────────────────────────
    client.test_event_code = test_event_code.strip() if test_event_code and test_event_code.strip() else None
    client.enable_facebook = (enable_facebook == "1")
    client.enable_tiktok = (enable_tiktok == "1")
    client.enable_ga4 = (enable_ga4 == "1")
    client.deferred_purchase = (deferred_purchase == "1")

    # Update domain(s) if provided
    if domain is not None:
        parts = []
        for raw_part in domain.split(","):
            d = raw_part.strip().lower()
            if not d:
                continue
            import re
            d = re.sub(r"^https?://", "", d).split("/", 1)[0].rstrip(".")
            if d.startswith("www."):
                d = d[4:]
            if d and ("." not in d or len(d) > 255):
                from urllib.parse import urlencode
                q = urlencode({"settings_msg": f"ভুল ডোমেন ফরম্যাট: {raw_part}", "settings_type": "error"})
                return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
            parts.append(d)
        client.domain = ",".join(parts) if parts else None

    # Update COD Auto-Confirm Settings
    client.auto_confirm_days = min(max(0, auto_confirm_days), 7)
    client.auto_confirm_status = auto_confirm_status.strip() or "completed"

    client.tiktok_pixel_id = tiktok_pixel_id.strip() if tiktok_pixel_id and tiktok_pixel_id.strip() else None
    client.tiktok_test_event_code = tiktok_test_event_code.strip() if tiktok_test_event_code and tiktok_test_event_code.strip() else None
    client.ga4_measurement_id = ga4_measurement_id.strip() if ga4_measurement_id and ga4_measurement_id.strip() else None

    # ─── Only update encrypted tokens if new value provided ──────────────────
    if access_token and access_token.strip():
        client.access_token = encrypt_token(access_token.strip())
    if tiktok_access_token and tiktok_access_token.strip():
        client.tiktok_access_token = encrypt_token(tiktok_access_token.strip())
    if ga4_api_secret and ga4_api_secret.strip():
        client.ga4_api_secret = encrypt_token(ga4_api_secret.strip())

    await db.commit()

    # Clear cache so changes take effect immediately
    from app.dependencies import clear_client_cache
    clear_client_cache(client.api_key)

    from urllib.parse import urlencode
    q = urlencode({"settings_msg": "✅ Settings সফলভাবে আপডেট হয়েছে!", "settings_type": "success"})
    return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
