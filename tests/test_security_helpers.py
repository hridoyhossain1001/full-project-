import hashlib
import hmac
import os
from datetime import datetime, timezone

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-api-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("ENCRYPTION_KEY", "ZFhnf1szwemka8kBbH9jPTC7oKBRTEv0EqWt1J8AD0M=")

from app.routers.admin import create_admin_csrf_token, mask_secret, verify_admin_csrf_token
from app.routers.events import _is_domain_allowed, _verify_capi_signature
from app.main import _is_tracker_path
from app import limiter as limiter_module
from starlette.requests import Request


def test_admin_csrf_token_round_trip():
    token = create_admin_csrf_token("admin")
    verify_admin_csrf_token(token, "admin")


def test_admin_csrf_rejects_tampering():
    token = create_admin_csrf_token("admin")
    bad_token = token[:-1] + ("0" if token[-1] != "0" else "1")

    try:
        verify_admin_csrf_token(bad_token, "admin")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("Tampered CSRF token was accepted")


def test_domain_matching_is_exact_or_real_subdomain():
    assert _is_domain_allowed("example.com", "example.com")
    assert _is_domain_allowed("shop.example.com", "example.com")
    assert not _is_domain_allowed("badexample.com", "example.com")
    assert not _is_domain_allowed("example.com.attacker.test", "example.com")


def test_tracker_path_matching_does_not_include_client_routes():
    assert _is_tracker_path("/c")
    assert _is_tracker_path("/c/batch")
    assert _is_tracker_path("/t.js")
    assert not _is_tracker_path("/client")
    assert not _is_tracker_path("/custom")


def test_proxy_ip_headers_are_ignored_unless_trusted(monkeypatch):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.10")],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )

    monkeypatch.setattr(limiter_module, "TRUST_PROXY_HEADERS", False)
    assert limiter_module._get_real_ip(request) == "127.0.0.1"

    monkeypatch.setattr(limiter_module, "TRUST_PROXY_HEADERS", True)
    assert limiter_module._get_real_ip(request) == "203.0.113.10"


def test_capi_signature_contract():
    body = b'{"data":[]}'
    api_key = "client-secret"
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(
        api_key.encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    assert _verify_capi_signature(body, api_key, timestamp, signature)


def test_mask_secret_keeps_edges_only():
    masked = mask_secret("abcdef1234567890")
    assert masked.startswith("abcdef")
    assert masked.endswith("7890")
    assert "123456" not in masked


def test_plugin_update_signature_contract():
    version = "1.1.1"
    download_url = "https://example.com/api/v1/plugin/download"
    package_sha256 = hashlib.sha256(b"zip-bytes").hexdigest()
    api_key = "client-secret"
    payload = f"{version}|{download_url}|{package_sha256}"

    signature = hmac.new(api_key.encode(), payload.encode(), hashlib.sha256).hexdigest()

    assert hmac.compare_digest(
        signature,
        hmac.new(api_key.encode(), payload.encode(), hashlib.sha256).hexdigest(),
    )


def test_domain_normalization():
    from app.utils.display import normalize_domain_input, display_domain_url

    assert normalize_domain_input("example.com") == "example.com"
    assert normalize_domain_input("https://www.example.com") == "example.com"
    assert normalize_domain_input("  www.example.com.  ") == "example.com"

    assert normalize_domain_input("example.com, google.com") == "example.com,google.com"
    assert normalize_domain_input("https://www.example.com, http://google.com") == "example.com,google.com"
    assert normalize_domain_input("  www.example.com. ,  ") == "example.com"
    assert normalize_domain_input(None) is None
    assert normalize_domain_input("   ") is None

    assert display_domain_url("example.com, google.com") == "https://www.example.com"
    assert display_domain_url("https://www.example.com") == "https://www.example.com"
    assert display_domain_url("") == ""
    assert display_domain_url(None) == ""
