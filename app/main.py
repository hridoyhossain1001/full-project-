import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import engine, Base
from app.routers.events import router as events_router
from app.routers.admin import router as admin_router
from app.routers.monitoring import router as monitoring_router
from app.routers.client_portal import router as client_portal_router
from app.routers.tracker import router as tracker_router
from app.routers.deferred_events import router as deferred_events_router
from app.routers.analytics import router as analytics_router
from app.routers.debug import router as debug_router
from app.limiter import limiter
import os

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
if not ADMIN_API_KEY:
    raise RuntimeError("ADMIN_API_KEY environment variable is required.")

ENABLE_DOCS = os.getenv("ENABLE_DOCS", "").lower() in ("true", "1", "yes")


def _csv_env(name: str, default: str) -> list[str]:
    values = os.getenv(name, default)
    return [value.strip() for value in values.split(",") if value.strip()]


ALLOWED_HOSTS = _csv_env(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1,testserver,*.herokuapp.com",
)

# ─── Logging Setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Lifespan: DB Table তৈরি হবে অ্যাপ স্টার্টে ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 CAPI Gateway স্টার্ট হচ্ছে...")

    # ─── Database Schema ──────────────────────────────────────────────────
    # Production-এ Alembic migration ব্যবহার করুন। create_all শুধু explicit
    # dev/initial setup-এর জন্য: ENABLE_CREATE_ALL=true.
    skip_create_all = os.getenv("SKIP_CREATE_ALL", "").lower() in ("true", "1", "yes")
    enable_create_all = os.getenv("ENABLE_CREATE_ALL", "").lower() in ("true", "1", "yes")
    if enable_create_all and not skip_create_all:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ ডাটাবেস টেবিল তৈরি/যাচাই সফল।")
    else:
        logger.info("ℹ️  create_all স্কিপ — Alembic migration ব্যবহার করুন।")

    # 🔄 Retry Service — শুধুমাত্র ENABLE_RETRY_IN_WEB=true হলে এই process-এ চলবে
    # Worker dyno না থাকলে Procfile-এ: web: ENABLE_RETRY_IN_WEB=true uvicorn ... --workers 1
    # অথবা Heroku config var-এ সেট করুন। একাধিক worker থাকলে retry duplicate হবে!
    import asyncio
    if os.getenv("ENABLE_OUTBOX_IN_WEB", "").lower() in ("true", "1", "yes"):
        from app.services.event_worker import process_event_outbox_forever
        asyncio.create_task(process_event_outbox_forever())
        logger.info("Outbox worker started in Web Process.")
    else:
        logger.info("Outbox worker disabled in Web Process (ENABLE_OUTBOX_IN_WEB not set).")

    if os.getenv("ENABLE_RETRY_IN_WEB", "").lower() in ("true", "1", "yes"):
        from app.services.retry_service import retry_failed_events
        asyncio.create_task(retry_failed_events())
        logger.info("⚙️  Background Retry Service স্টার্ট হয়েছে (Web Process)।")
    else:
        logger.info("ℹ️  Retry Service এই process-এ নিষ্ক্রিয় (ENABLE_RETRY_IN_WEB সেট নেই)।")

    if os.getenv("ENABLE_MAINTENANCE_IN_WEB", "").lower() in ("true", "1", "yes"):
        # 🧹 Auto-Cleanup Service
        from app.services.cleanup_service import auto_cleanup_database
        asyncio.create_task(auto_cleanup_database())
        logger.info("🧹 Background Auto-Cleanup Service স্টার্ট হয়েছে (Web Process)।")

        # ⏰ Pending Events Auto-Expiry Service
        from app.services.expiry_service import expire_old_pending_events
        asyncio.create_task(expire_old_pending_events())
        logger.info("⏰ Pending Events Expiry Service স্টার্ট হয়েছে (Web Process)।")
    else:
        logger.info("ℹ️  Maintenance loops web process-এ নিষ্ক্রিয়; worker process ব্যবহার করুন।")

    # 🌍 GeoIP Database Load
    from app.services.geoip_service import download_geoip_db_if_missing, close_geoip_db
    await download_geoip_db_if_missing()

    yield

    # Shutdown — cleanup
    # 🔒 HTTP client বন্ধ করো
    from app.services.capi_service import close_http_client
    await close_http_client()
    close_geoip_db()

    logger.info("🛑 CAPI Gateway বন্ধ হচ্ছে...")
    await engine.dispose()


# ─── FastAPI App (ORJSONResponse = 2-3x faster JSON serialization) ────────
app = FastAPI(
    title="CAPI Gateway",
    description="Multi-tenant Facebook Conversion API Gateway — Server-Side Tracking as a Service",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
    default_response_class=ORJSONResponse,  # 🚀 orjson = C-based, 2-3x faster!
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS,
)

# ─── CORS — Multi-Tenant Tracker: allow_origins=["*"] ইচ্ছাকৃত ─────────────
# ব্রাউজার ট্র্যাকার (t.js) যেকোনো ক্লায়েন্ট ওয়েবসাইট থেকে cross-origin request পাঠায়।
# Deploy-time-এ সব ক্লায়েন্ট ডোমেইন জানা সম্ভব নয়, তাই CORS open রাখা হয়েছে।
# প্রকৃত নিরাপত্তা → per-client domain whitelisting (events.py ও tracker.py-তে enforce হয়)।
# Client Portal same-origin cookie ব্যবহার করে; public tracker CORS-এ credentials লাগে না।
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "X-API-Key",
        "X-CAPI-Origin",
        "X-CAPI-Timestamp",
        "X-CAPI-Signature",
        "Content-Type",
    ],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(events_router, prefix="/api/v1", tags=["Events"])
app.include_router(admin_router,  prefix="/api/v1", tags=["Admin"])
app.include_router(monitoring_router, prefix="/api/v1", tags=["Monitoring"])
app.include_router(client_portal_router, tags=["Client Portal"])
app.include_router(tracker_router, tags=["Tracker"])  # /t.js, /c — root level, no prefix
app.include_router(deferred_events_router, prefix="/api/v1", tags=["Deferred Events"])
app.include_router(analytics_router, prefix="/api/v1", tags=["Analytics"])
app.include_router(debug_router, prefix="/api/v1", tags=["Debug & Testing"])

from app.routers.plugin import router as plugin_router
app.include_router(plugin_router, prefix="/api/v1", tags=["Plugin"])

from app.routers.webhook import router as webhook_router
app.include_router(webhook_router, prefix="/api/v1", tags=["Webhook"])

from app.routers.client_health import router as client_health_router
app.include_router(client_health_router, prefix="/api/v1", tags=["Client Health"])


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status": "running",
        "service": "CAPI Gateway",
        "version": "1.1.0",
        "message": "🔥 Server-Side Tracking Gateway চলছে!",
    }
