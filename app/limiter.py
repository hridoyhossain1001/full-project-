from slowapi import Limiter
from fastapi import Request


def _get_real_ip(request: Request) -> str:
    """
    রিভার্স প্রক্সি (Cloudflare / Nginx / AWS ALB) এর পেছনে ব্যবহারকারীর আসল IP বের করে।
    Fallback chain: CF-Connecting-IP → X-Forwarded-For (first IP) → raw socket host
    """
    # Cloudflare — সবচেয়ে নির্ভরযোগ্য, কারণ CF নিজে এটি সেট করে
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # Nginx / AWS Load Balancer / Standard Proxy
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # প্রথম IP-ই ক্লায়েন্টের আসল IP (বাকিগুলো প্রক্সি চেইন)
        return forwarded_for.split(",")[0].strip()

    # Fallback — সরাসরি কানেকশন (লোকাল ডেভ বা টেস্ট)
    return request.client.host if request.client else "unknown"


# Single shared rate limiter instance — used by both main.py and routers
limiter = Limiter(key_func=_get_real_ip)
