import asyncio
import logging
import ipaddress
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.services.capi_service import get_http_client

logger = logging.getLogger(__name__)


_dns_global_cache: dict[str, bool] = {}


async def _hostname_is_global(host: str) -> bool:
    """Check if hostname resolves to global (non-private) IP addresses.
    Results are cached and DNS resolution runs off the event loop.
    """
    if host in _dns_global_cache:
        return _dns_global_cache[host]

    try:
        loop = asyncio.get_running_loop()
        addrinfos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        _dns_global_cache[host] = False
        return False

    addresses = {info[4][0] for info in addrinfos}
    if not addresses:
        _dns_global_cache[host] = False
        return False

    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                _dns_global_cache[host] = False
                return False
        except ValueError:
            _dns_global_cache[host] = False
            return False
    if len(_dns_global_cache) >= 256:
        _dns_global_cache.clear()
    _dns_global_cache[host] = True
    return True


async def _webhook_url_allowed(webhook_url: str) -> bool:
    parsed = urlparse(webhook_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        return await _hostname_is_global(host)


async def send_webhook(webhook_url: str, event_type: str, data: dict) -> bool:
    """Custom webhook URL-এ event data পাঠায়। Shared HTTP client ব্যবহার করে।"""
    if not webhook_url:
        return False
    if not await _webhook_url_allowed(webhook_url):
        logger.warning("Rejected unsafe webhook URL")
        return False

    payload = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "source": "capi_gateway",
    }

    try:
        http_client = await get_http_client()
        resp = await http_client.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0,
            follow_redirects=False,
        )
        logger.info(f"🔗 Webhook sent to {webhook_url[:40]}... status={resp.status_code}")
        return resp.status_code < 400
    except Exception as e:
        logger.error(f"🔗 Webhook send error: {e}")
        return False
