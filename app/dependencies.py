import time
import logging
from dataclasses import dataclass
from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.client import Client
from app.security import decrypt_token

logger = logging.getLogger(__name__)

# ─── In-Memory API Key Cache ────────────────────────────────────────────────
# প্রতি request-এ DB query বাদ দিতে TTL-based cache
# ORM object cache করলে DetachedInstanceError হতে পারে,
# তাই plain dataclass cache করা হয়। DB থেকে আনা Client-এর সব প্রয়োজনীয় field কপি করে রাখে।


@dataclass(frozen=True, slots=True)
class CachedClient:
    """Lightweight snapshot of a Client row — safe to cache across requests."""
    id: int
    name: str
    api_key: str
    public_key: str | None
    portal_key: str | None
    pixel_id: str
    access_token: str
    test_event_code: str | None          # Facebook test event code
    tiktok_test_event_code: str | None   # TikTok test event code (আলাদা)
    is_active: bool
    domain: str | None
    rate_limit: int
    daily_quota: int
    monthly_limit: int | None
    tiktok_pixel_id: str | None
    tiktok_access_token: str | None
    ga4_measurement_id: str | None
    ga4_api_secret: str | None
    deferred_purchase: bool
    webhook_url: str | None


_client_cache: dict[str, tuple[CachedClient, float]] = {}
CACHE_TTL = 60  # 60 সেকেন্ড — client info cache করে রাখো

def clear_client_cache(api_key: str):
    """Admin update-এর পর cache ক্লিয়ার করতে ব্যবহৃত হয়"""
    for cache_key, (cached, _) in list(_client_cache.items()):
        if cache_key == api_key or cached.api_key == api_key:
            del _client_cache[cache_key]

def _snapshot(client: Client) -> CachedClient:
    """ORM object থেকে plain dataclass তৈরি করো — session-independent।"""
    return CachedClient(
        id=client.id,
        name=client.name,
        api_key=client.api_key,
        public_key=getattr(client, 'public_key', None),
        portal_key=getattr(client, 'portal_key', None),
        pixel_id=client.pixel_id,
        access_token=client.access_token,
        test_event_code=client.test_event_code,
        tiktok_test_event_code=getattr(client, 'tiktok_test_event_code', None),
        is_active=client.is_active,
        domain=client.domain,
        rate_limit=client.rate_limit or 5000,
        daily_quota=client.daily_quota or 100000,
        monthly_limit=getattr(client, 'monthly_limit', None),
        tiktok_pixel_id=getattr(client, 'tiktok_pixel_id', None),
        tiktok_access_token=getattr(client, 'tiktok_access_token', None),
        ga4_measurement_id=getattr(client, 'ga4_measurement_id', None),
        ga4_api_secret=getattr(client, 'ga4_api_secret', None),
        deferred_purchase=getattr(client, 'deferred_purchase', False) or False,
        webhook_url=getattr(client, 'webhook_url', None),
    )


async def get_current_client(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> CachedClient:
    """
    প্রতিটি /events রিকোয়েস্টে X-API-Key হেডার চেক করে
    ক্লায়েন্ট ভেরিফাই করে।
    In-memory cache দিয়ে DB query minimize করে (60s TTL)।
    CachedClient রিটার্ন করে — SQLAlchemy session-এ নির্ভর করে না।
    """
    if not x_api_key:
        encrypted_session = request.cookies.get("client_session")
        if encrypted_session:
            try:
                decrypted = decrypt_token(encrypted_session, allow_legacy_plaintext=False)
            except Exception:
                decrypted = None
            if decrypted and decrypted.startswith("client:"):
                import secrets
                try:
                    _, client_id_str, session_secret = decrypted.split(":", 2)
                    result = await db.execute(select(Client).where(Client.id == int(client_id_str)))
                    portal_client = result.scalar_one_or_none()
                    
                    if portal_client:
                        expected_secret = getattr(portal_client, "portal_key", None)
                        if expected_secret and secrets.compare_digest(session_secret, expected_secret):
                            x_api_key = portal_client.api_key
                        elif not expected_secret and secrets.compare_digest(session_secret, portal_client.api_key):
                            x_api_key = portal_client.api_key
                except (TypeError, ValueError):
                    pass
            else:
                x_api_key = decrypted

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API Key প্রয়োজন। X-API-Key header পাঠান।"
        )

    # ─── Cache থেকে চেক করো আগে ─────────────────────────────────────
    now = time.time()
    if x_api_key in _client_cache:
        cached, cached_at = _client_cache[x_api_key]
        if now - cached_at < CACHE_TTL:
            # Cache hit — DB query বাদ!
            if cached.is_active:
                return cached
            else:
                # Cache-এ আছে কিন্তু inactive — remove & reject
                del _client_cache[x_api_key]
                raise HTTPException(
                    status_code=401,
                    detail="Invalid বা Inactive API Key।"
                )

    # ─── Cache miss — DB query ─────────────────────────────────────────
    result = await db.execute(
        select(Client).where(
            Client.api_key == x_api_key,
            Client.is_active == True
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=401,
            detail="Invalid বা Inactive API Key।"
        )

    # ─── Cache-এ রাখো (plain dataclass — safe across sessions) ──────
    cached = _snapshot(client)
    _client_cache[x_api_key] = (cached, now)
    return cached
