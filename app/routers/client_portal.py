from fastapi import APIRouter, Depends, Request, Form, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
import datetime
import secrets
import logging
from typing import Optional

from app.database import get_db

logger = logging.getLogger(__name__)
from app.models.client import Client
from app.models.client_user import ClientUser
from app.models.event_log import EventLog
from app.models.pending_event import PendingEvent
from app.utils.display import display_domain_url, mask_secret
from app.security import encrypt_token, decrypt_token
from app.routers.client_auth import (
    _clean_domain,
    _clean_name,
    _clear_session_cookie,
    _create_session,
    _validate_email,
    _validate_password,
    get_client_user_from_cookie,
)
from app.services.auth_service import hash_password, verify_password
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
    try:
        _, client, _ = await get_client_user_from_cookie(request, db)
        return client
    except HTTPException as e:
        if e.status_code != 401:
            raise

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
async def client_login_page(request: Request, db: AsyncSession = Depends(get_db)):
    client = await get_client_from_portal_session(request, db)
    if client:
        return RedirectResponse(url="/client/dashboard", status_code=303)

    return templates.TemplateResponse(
        request,
        "client_portal/login.html",
        {"title": "Client Login", "active_tab": "login"}
    )


@router.post("/client/login", include_in_schema=False)
@limiter.limit("5/minute")
async def client_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        email = _validate_email(email)
        result = await db.execute(select(ClientUser).where(ClientUser.email == email))
        user = result.scalar_one_or_none()
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                request,
                "client_portal/login_failed.html",
                {"title": "Login Failed", "message": "Invalid email or password."},
                status_code=401
            )

        client_r = await db.execute(select(Client).where(Client.id == user.client_id))
        client = client_r.scalar_one_or_none()
        if not client or not client.is_active:
            return templates.TemplateResponse(
                request,
                "client_portal/login_failed.html",
                {"title": "Login Failed", "message": "This workspace is inactive."},
                status_code=401
            )

        redirect = RedirectResponse(url="/client/dashboard", status_code=303)
        user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
        await _create_session(db, user, redirect, request)
        await db.commit()
        return redirect
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "client_portal/login_failed.html",
            {"title": "Login Failed", "message": exc.detail},
            status_code=exc.status_code
        )
    except Exception as exc:
        logger.error(f"Login failed: {exc}", exc_info=True)
        return templates.TemplateResponse(
            request,
            "client_portal/login_failed.html",
            {"title": "Login Error", "message": "An unexpected error occurred during login. Please try again."},
            status_code=500
        )


@router.post("/client/signup", include_in_schema=False)
@limiter.limit("5/minute")
async def client_signup_form(
    request: Request,
    full_name: str = Form(...),
    business_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    domain: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    try:
        try:
            clean_email = _validate_email(email)
            _validate_password(password)
            if password != confirm_password:
                raise HTTPException(status_code=400, detail="Passwords do not match.")
            clean_full_name = _clean_name(full_name, "Full name")
            clean_business_name = _clean_name(business_name, "Business name")
            clean_domain = _clean_domain(domain)
        except HTTPException as exc:
            return templates.TemplateResponse(
                request,
                "client_portal/login.html",
                {"title": "Client Login", "active_tab": "signup", "error": exc.detail},
                status_code=400,
            )

        existing = await db.execute(select(ClientUser).where(ClientUser.email == clean_email))
        if existing.scalar_one_or_none():
            return templates.TemplateResponse(
                request,
                "client_portal/login.html",
                {
                    "title": "Client Login",
                    "active_tab": "signup",
                    "error": "An account already exists for this email.",
                },
                status_code=409,
            )

        client = Client(
            name=clean_business_name,
            pixel_id="0",
            access_token=encrypt_token("pending_setup"),
            domain=clean_domain,
            api_key=secrets.token_urlsafe(32),
            public_key=secrets.token_urlsafe(24),
            portal_key=secrets.token_urlsafe(24),  # FIXED portal_key from None
            enable_facebook=False,
            enable_tiktok=False,
            enable_ga4=False,
            monthly_limit=1000,
            daily_quota=1000,
            rate_limit=120,
        )
        db.add(client)
        await db.flush()

        user = ClientUser(
            client_id=client.id,
            email=clean_email,
            password_hash=hash_password(password),
            full_name=clean_full_name,
            role="owner",
            is_active=True,
            email_verified=False,
        )
        db.add(user)
        await db.flush()

        redirect = RedirectResponse(url="/client/dashboard", status_code=303)
        await _create_session(db, user, redirect, request)
        await db.commit()
        return redirect
    except Exception as exc:
        logger.error(f"Signup failed: {exc}", exc_info=True)
        return templates.TemplateResponse(
            request,
            "client_portal/login.html",
            {
                "title": "Client Login",
                "active_tab": "signup",
                "error": "An unexpected error occurred during signup. Please try again.",
            },
            status_code=500,
        )


@router.get("/client/logout", include_in_schema=False)
async def client_logout(request: Request):
    redirect = RedirectResponse(url="/client", status_code=303)
    redirect.delete_cookie("client_session")
    redirect.delete_cookie("buykori_client_session", path="/")
    _clear_session_cookie(redirect, request)
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

    # ─── CSRF & Origin Validation ──────────────────────────────────────────
    from urllib.parse import urlparse, urlencode
    referer = request.headers.get("referer")
    origin = request.headers.get("origin")

    # Enforce allowed Origin/Referer matching to protect against cross-site request forgery
    from app.routers.client_auth import ALLOWED_CLIENT_AUTH_HOSTS
    valid_host = False
    for header_val in (origin, referer):
        if header_val:
            host = (urlparse(header_val).hostname or "").lower()
            if host in ALLOWED_CLIENT_AUTH_HOSTS:
                valid_host = True
                break

    if not valid_host:
        q = urlencode({"settings_msg": "CSRF protection: Invalid or missing Origin/Referer.", "settings_type": "error"})
        return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)

    # ─── Validate Facebook Pixel ID if provided ────────────────────────────
    if pixel_id and pixel_id.strip():
        if not pixel_id.strip().isdigit():
            q = urlencode({"settings_msg": "Facebook Pixel ID must be numeric (only digits).", "settings_type": "error"})
            return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
        client.pixel_id = pixel_id.strip()

    # ─── Validate TikTok Pixel ID if provided ──────────────────────────────
    if tiktok_pixel_id and tiktok_pixel_id.strip():
        if not tiktok_pixel_id.strip().isdigit():
            q = urlencode({"settings_msg": "TikTok Pixel ID must be numeric (only digits).", "settings_type": "error"})
            return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
        client.tiktok_pixel_id = tiktok_pixel_id.strip()
    else:
        client.tiktok_pixel_id = None

    # ─── Validate GA4 Measurement ID if provided ───────────────────────────
    if ga4_measurement_id and ga4_measurement_id.strip():
        val = ga4_measurement_id.strip().upper()
        import re
        if not re.match(r"^G-[A-Z0-9]+$", val):
            q = urlencode({"settings_msg": "GA4 Measurement ID must follow 'G-XXXXXX' format.", "settings_type": "error"})
            return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
        client.ga4_measurement_id = val
    else:
        client.ga4_measurement_id = None

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
                q = urlencode({"settings_msg": f"Incorrect domain format: {raw_part}", "settings_type": "error"})
                return RedirectResponse(url=f"/client/dashboard?{q}#settings", status_code=303)
            parts.append(d)
        client.domain = ",".join(parts) if parts else None

    # Update COD Auto-Confirm Settings
    client.auto_confirm_days = min(max(0, auto_confirm_days), 7)
    client.auto_confirm_status = auto_confirm_status.strip() or "completed"

    client.tiktok_test_event_code = tiktok_test_event_code.strip() if tiktok_test_event_code and tiktok_test_event_code.strip() else None

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
