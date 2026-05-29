import asyncio
import ipaddress
import logging
import os
import random
import socket
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.services.capi_service import get_http_client

logger = logging.getLogger(__name__)

WEBHOOK_ALLOW_HTTP = os.getenv("WEBHOOK_ALLOW_HTTP", "false").strip().lower() in {"1", "true", "yes"}
_dns_global_cache: OrderedDict[str, bool] = OrderedDict()


async def _resolve_global_addresses(host: str) -> set[str] | None:
    try:
        loop = asyncio.get_running_loop()
        addrinfos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    addresses = {info[4][0] for info in addrinfos}
    if not addresses:
        return None

    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                return None
        except ValueError:
            return None
    return addresses


async def _hostname_is_global(host: str) -> bool:
    if host in _dns_global_cache:
        _dns_global_cache.move_to_end(host)
        return _dns_global_cache[host]

    allowed = bool(await _resolve_global_addresses(host))
    if len(_dns_global_cache) >= 256:
        _dns_global_cache.popitem(last=False)
    _dns_global_cache[host] = allowed
    return allowed


def _basic_webhook_url_allowed(parsed) -> bool:
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return False
    if parsed.scheme == "http" and not WEBHOOK_ALLOW_HTTP:
        return False
    if parsed.username or parsed.password:
        return False

    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return False
    return True


async def _webhook_url_allowed(webhook_url: str) -> bool:
    parsed = urlparse(webhook_url)
    if not _basic_webhook_url_allowed(parsed):
        return False

    host = parsed.hostname.lower()
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        return await _hostname_is_global(host)


async def _webhook_url_allowed_now(parsed) -> bool:
    host = parsed.hostname.lower()
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        return bool(await _resolve_global_addresses(host))


async def send_webhook(webhook_url: str, event_type: str, data: dict) -> bool:
    if not webhook_url:
        return False

    parsed = urlparse(webhook_url)
    if not _basic_webhook_url_allowed(parsed):
        logger.warning("Rejected unsafe webhook URL")
        return False

    # Re-resolve immediately before sending. This keeps normal HTTPS SNI and
    # certificate verification intact while rejecting private/local targets.
    if not await _webhook_url_allowed_now(parsed):
        logger.warning("Rejected webhook URL because it resolves to a non-global address")
        return False

    payload = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "source": "capi_gateway",
    }

    max_attempts = 4
    base_delay = 1.0

    for attempt in range(1, max_attempts + 1):
        try:
            http_client = await get_http_client()
            resp = await http_client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10.0,
                follow_redirects=False,
            )

            if resp.status_code < 400:
                logger.info("Webhook sent status=%s after %d attempt(s)", resp.status_code, attempt)
                return True
            else:
                logger.warning("Webhook failed status=%s on attempt %d", resp.status_code, attempt)
                if attempt == max_attempts:
                    return False
        except Exception as exc:
            logger.warning("Webhook send error on attempt %d: %s", attempt, exc)
            if attempt == max_attempts:
                return False

        # Exponential backoff with jitter
        delay = base_delay * (2 ** (attempt - 1))
        jitter = random.uniform(0.1, 0.5) * delay
        sleep_time = delay + jitter
        logger.info("Retrying webhook in %.2fs...", sleep_time)
        await asyncio.sleep(sleep_time)

    return False
