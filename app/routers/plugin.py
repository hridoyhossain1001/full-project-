"""WordPress plugin download and update-check endpoints."""

import hashlib
import hmac
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["Plugin"])

# Keep the update version tied to the packaged plugin. A stale Heroku
# PLUGIN_VERSION config var can hide available updates from WordPress.
PLUGIN_VERSION = "1.1.6"
PLUGIN_ZIP_PATH = Path(
    os.getenv(
        "PLUGIN_ZIP_PATH",
        str(Path(__file__).resolve().parents[2] / "wordpress-plugin" / "capi-gateway.zip"),
    )
)
PLUGIN_DOWNLOAD_URL = os.getenv("PLUGIN_DOWNLOAD_URL", "")


@router.get(
    "/plugin/update-check",
    summary="Check for plugin updates",
    description="Return WordPress plugin update metadata for the built-in auto-updater.",
)
async def plugin_update_check(
    request: Request,
    x_api_key: str = Header("", alias="X-API-Key"),
):
    """Return current plugin version info for WordPress auto-updater."""
    download_url = PLUGIN_DOWNLOAD_URL or _plugin_download_url(request)
    package_sha256 = ""
    if PLUGIN_ZIP_PATH.is_file():
        package_sha256 = hashlib.sha256(PLUGIN_ZIP_PATH.read_bytes()).hexdigest()

    signature = ""
    if x_api_key and package_sha256:
        payload = f"{PLUGIN_VERSION}|{download_url}|{package_sha256}"
        signature = hmac.new(
            x_api_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    return _plugin_update_response(download_url, package_sha256, signature)


def _plugin_download_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}/api/v1/plugin/download"


def _plugin_update_response(download_url: str, package_sha256: str, signature: str) -> JSONResponse:
    return JSONResponse(content={
        "version": PLUGIN_VERSION,
        "download_url": download_url,
        "package_sha256": package_sha256,
        "signature": signature,
        "homepage": "https://buykori.me/",
        "requires": "5.8",
        "tested": "6.7",
        "requires_php": "7.4",
        "last_updated": "2026-05-19",
        "description": "Server-Side Facebook CAPI, TikTok, and GA4 tracking for WooCommerce with deferred purchase support.",
        "changelog": (
            "<h4>v1.1.6</h4><ul>"
            "<li>Added UTM campaign capture and persistence for attribution reporting</li>"
            "<li>Added campaign source detection for TikTok and Facebook click IDs</li>"
            "<li>Added platform delivery controls support from the gateway</li>"
            "</ul>"
            "<h4>v1.1.5</h4><ul>"
            "<li>Added a Check Update Now tool to clear plugin update cache from the settings page</li>"
            "<li>Added manual update-cache reset so admins do not need to run database queries</li>"
            "</ul>"
            "<h4>v1.1.4</h4><ul>"
            "<li>Improved TikTok event payloads with richer product contents, content IDs, and content type</li>"
            "<li>Added checkout/customer field capture for better TikTok and Facebook event matching</li>"
            "<li>Rebuilt plugin update package so WordPress can detect the latest update</li>"
            "</ul>"
            "<h4>v1.1.3</h4><ul>"
            "<li>Added customer PII fields capture (email, phone, name, address, etc.) for AJAX tracking events</li>"
            "<li>Added nested contents array support to browser events (AddToCart, ViewContent, InitiateCheckout, etc.)</li>"
            "<li>Improved TikTok payload content mapping to follow Events API specifications</li>"
            "</ul>"
            "<h4>v1.1.2</h4><ul>"
            "<li>Durable outbox-friendly tracking improvements</li>"
            "<li>TikTok _ttp and ttclid capture for standard and custom events</li>"
            "<li>Lightweight AJAX rate limiting for frontend tracking</li>"
            "<li>Improved checkout/cart payloads and custom event stability</li>"
            "</ul>"
            "<h4>v1.1.0</h4><ul>"
            "<li>Purchase event blocking request response verification</li>"
            "<li>Phone hash normalization fix</li>"
            "<li>WooCommerce webhook HMAC signature verification</li>"
            "<li>Atomic rate limiting and production database safety</li>"
            "</ul>"
            "<h4>v1.0.0</h4><ul>"
            "<li>Initial release</li>"
            "<li>PageView, ViewContent, AddToCart, InitiateCheckout, Purchase tracking</li>"
            "<li>Deferred Purchase with auto-confirm</li>"
            "<li>Action Scheduler retry queue</li>"
            "</ul>"
        ),
    })


@router.get(
    "/plugin/download",
    summary="Download WordPress plugin ZIP",
    include_in_schema=False,
)
async def plugin_download():
    """Serve the packaged WordPress plugin ZIP for the auto-updater."""
    if not PLUGIN_ZIP_PATH.is_file():
        raise HTTPException(status_code=404, detail="Plugin ZIP not found")

    return FileResponse(
        path=PLUGIN_ZIP_PATH,
        media_type="application/zip",
        filename="capi-gateway.zip",
    )
