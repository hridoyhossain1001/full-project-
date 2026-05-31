import os

from slowapi import Limiter
from fastapi import Request


TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")


def _get_real_ip(request: Request) -> str:
    """
    রিভার্স প্রক্সি (Cloudflare / Nginx / AWS ALB) এর পেছনে ব্যবহারকারীর আসল IP বের করে।
    Fallback chain: CF-Connecting-IP → X-Forwarded-For (first IP) → raw socket host
    """
    if TRUST_PROXY_HEADERS:
        # These headers are safe only when the edge proxy overwrites client input.
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    # Fallback — সরাসরি কানেকশন (লোকাল ডেভ বা টেস্ট)
    return request.client.host if request.client else "unknown"


# Single shared rate limiter instance — used by both main.py and routers
limiter = Limiter(key_func=_get_real_ip)
