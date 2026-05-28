import asyncio
import httpx
import logging
import os
from typing import List
from app.schemas.event import EventData
from app.security import decrypt_token

logger = logging.getLogger(__name__)

FACEBOOK_API_VERSION = os.getenv("FACEBOOK_API_VERSION", "v21.0")
HTTP_MAX_CONNECTIONS = int(os.getenv("HTTP_MAX_CONNECTIONS", "20"))
HTTP_MAX_KEEPALIVE_CONNECTIONS = int(os.getenv("HTTP_MAX_KEEPALIVE_CONNECTIONS", "10"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15.0"))

# ─── Global Persistent HTTP Client ─────────────────────────────────────────
# TCP connection reuse + HTTP/2 multiplexing = 3-5x faster Facebook API calls
# প্রতি request-এ নতুন connection না খুলে reuse করে
_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """Singleton httpx client — connection pooling + HTTP/2 সাপোর্ট সহ"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _http_client_lock:
            # Double-checked locking — another coroutine may have created it
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT_SECONDS,
                    limits=httpx.Limits(
                        max_connections=HTTP_MAX_CONNECTIONS,
                        max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                    ),
                    http2=True,  # HTTP/2 multiplexing — একটা connection-এ multiple request!
                )
    return _http_client


async def close_http_client():
    """App shutdown-এর সময় client বন্ধ করো"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
        logger.info("🔒 HTTP client বন্ধ হয়েছে।")


async def send_to_facebook(client, events: List[EventData]) -> dict:
    """
    ক্লায়েন্টের Pixel ID ও Access Token ব্যবহার করে
    Facebook CAPI-তে ইভেন্ট পাঠায়।
    Persistent connection pool ব্যবহার করে — TCP reuse + HTTP/2।
    """
    url = (
        f"https://graph.facebook.com/{FACEBOOK_API_VERSION}"
        f"/{client.pixel_id}/events"
    )

    # ইভেন্ট ডাটা প্রস্তুত করা
    events_data = [event.model_dump(exclude_none=True) for event in events]
    for e in events_data:
        e.pop("emq_score", None)

    payload = {
        "data": events_data,
        "access_token": decrypt_token(client.access_token),  # 🔐 Decrypt before sending
    }

    # Test Event Code থাকলে যোগ করো (FB Events Manager-এ টেস্ট করার সময়)
    if client.test_event_code:
        payload["test_event_code"] = client.test_event_code

    try:
        http_client = await get_http_client()
        response = await http_client.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        logger.debug(
            f"[{client.name}] {len(events)} ইভেন্ট পাঠানো সফল। "
            f"FB Response: {result}"
        )
        return result

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[{client.name}] Facebook API Error: {e.response.status_code} - {e.response.text}"
        )
        raise

    except httpx.RequestError as e:
        logger.error(f"[{client.name}] Network Error: {str(e)}")
        raise
