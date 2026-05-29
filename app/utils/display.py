"""
Shared display/formatting utilities — used by admin, client_portal, and templates.
Extracted from admin.py to avoid cross-router import coupling.
"""

import re
from urllib.parse import urlparse

DOUBLE_TLDS = {
    "co.uk", "me.uk", "org.uk", "ltd.uk", "plc.uk", "net.uk",
    "com.bd", "edu.bd", "gov.bd", "org.bd", "net.bd",
    "com.au", "net.au", "org.au", "gov.au", "edu.au",
    "co.jp", "ne.jp", "or.jp", "go.jp", "ac.jp",
    "com.br", "net.br", "org.br",
    "co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in",
    "com.sg", "net.sg", "org.sg",
    "com.tr", "net.tr", "org.tr",
    "com.ua", "net.ua", "org.ua",
}


def is_ip_address(host: str) -> bool:
    """Check if host is an IPv4 or IPv6 address."""
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
        return True
    if ":" in host:
        return True
    return False


def should_prepend_www(host: str) -> bool:
    """Determine if 'www.' should be prepended to the host name.
    Do not prepend to localhost, IP addresses, or subdomains.
    """
    if host == "localhost":
        return False
    if is_ip_address(host):
        return False

    parts = host.split(".")
    if len(parts) < 2:
        return False
    elif len(parts) == 2:
        # Standard root domain, e.g., example.com
        return True
    elif len(parts) == 3:
        # Check if the last two parts form a double TLD
        suffix = f"{parts[-2]}.{parts[-1]}"
        if suffix in DOUBLE_TLDS:
            return True
        return False
    else:
        # 4 or more parts (definitely a subdomain, e.g., sub.example.co.uk)
        return False


def normalize_domain_input(domain: str | None) -> str | None:
    """Domain input normalize করে — www, trailing dots, protocol সরায়।
    যদি comma-separated multiple domains থাকে, তবে প্রত্যেকটি ডোমেনকে normalize করে comma দিয়ে যুক্ত করে।
    """
    if not domain or not domain.strip():
        return None

    raw = domain.strip().lower()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None

    normalized_parts = []
    for part in parts:
        # Prepend protocol if missing to allow urlparse to extract hostname correctly
        p_str = part if "://" in part else f"https://{part}"
        try:
            parsed = urlparse(p_str)
            host = parsed.hostname or parsed.path
        except Exception:
            host = part

        if not host:
            continue

        # Clean host (remove port if it fell back to parsed.path, strip trailing dots, strip whitespaces)
        host = host.split(":")[0].strip().rstrip(".")

        # Remove leading "www." if present
        if host.startswith("www."):
            host = host[4:]

        # Clean any trailing/leading slashes
        host = host.strip("/")

        if host:
            normalized_parts.append(host)

    return ",".join(normalized_parts) if normalized_parts else None


def display_domain_url(domain: str | None) -> str:
    """Domain থেকে display URL তৈরি করে (e.g., https://www.example.com)।
    যদি একাধিক comma-separated domains থাকে, তবে প্রথম ডোমেনটি নিয়ে কাজ করে।
    """
    if not domain:
        return ""
    parts = [p.strip() for p in domain.split(",") if p.strip()]
    if not parts:
        return ""
    first_domain = normalize_domain_input(parts[0])
    if not first_domain:
        return ""

    if should_prepend_www(first_domain):
        return f"https://www.{first_domain}"
    return f"https://{first_domain}"


def mask_secret(value: str | None, prefix: int = 6, suffix: int = 4) -> str:
    """Secret value-এর মাঝে bullet দিয়ে মাস্ক করে।"""
    if not value:
        return ""
    if len(value) <= prefix + suffix:
        return "•" * len(value)
    return f"{value[:prefix]}{'•' * 12}{value[-suffix:]}"
