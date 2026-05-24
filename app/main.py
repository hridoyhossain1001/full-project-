import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
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
from app.routers.client_auth import router as client_auth_router
from app.limiter import limiter
import os
import asyncio

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
if not ADMIN_API_KEY:
    raise RuntimeError("ADMIN_API_KEY environment variable is required.")

ENABLE_DOCS = os.getenv("ENABLE_DOCS", "").lower() in ("true", "1", "yes")


def _csv_env(name: str, default: str) -> list[str]:
    values = os.getenv(name, default)
    return [value.strip() for value in values.split(",") if value.strip()]


ALLOWED_HOSTS = _csv_env(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1,testserver,*.herokuapp.com,buykori.app,www.buykori.app,client.buykori.app,admin.buykori.app,api.buykori.app,track.buykori.app",
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
    logger.info("🚀 Buykori AdSync স্টার্ট হচ্ছে...")

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

    # ─── Background Task Management ────────────────────────────────────
    # Store references so tasks aren't garbage collected and add error callbacks
    _background_tasks: set[asyncio.Task] = set()

    def _task_done_callback(task: asyncio.Task) -> None:
        _background_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.critical(f"🔥 Background task {task.get_name()} died: {exc!r}")

    def _launch(coro, *, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        _background_tasks.add(task)
        task.add_done_callback(_task_done_callback)
        return task

    # 🔄 Retry Service — শুধুমাত্র ENABLE_RETRY_IN_WEB=true হলে এই process-এ চলবে
    # Worker dyno না থাকলে Procfile-এ: web: ENABLE_RETRY_IN_WEB=true uvicorn ... --workers 1
    # অথবা Heroku config var-এ সেট করুন। একাধিক worker থাকলে retry duplicate হবে!
    if os.getenv("ENABLE_OUTBOX_IN_WEB", "").lower() in ("true", "1", "yes"):
        from app.services.event_worker import process_event_outbox_forever
        _launch(process_event_outbox_forever(), name="outbox-worker")
        logger.info("Outbox worker started in Web Process.")
    else:
        logger.info("Outbox worker disabled in Web Process (ENABLE_OUTBOX_IN_WEB not set).")

    if os.getenv("ENABLE_RETRY_IN_WEB", "").lower() in ("true", "1", "yes"):
        from app.services.retry_service import retry_failed_events
        _launch(retry_failed_events(), name="retry-worker")
        logger.info("⚙️  Background Retry Service স্টার্ট হয়েছে (Web Process)।")
    else:
        logger.info("ℹ️  Retry Service এই process-এ নিষ্ক্রিয় (ENABLE_RETRY_IN_WEB সেট নেই)।")

    if os.getenv("ENABLE_MAINTENANCE_IN_WEB", "").lower() in ("true", "1", "yes"):
        # 🧹 Auto-Cleanup Service
        from app.services.cleanup_service import auto_cleanup_database
        _launch(auto_cleanup_database(), name="cleanup-worker")
        logger.info("🧹 Background Auto-Cleanup Service স্টার্ট হয়েছে (Web Process)।")

        # ⏰ Pending Events Auto-Expiry Service
        from app.services.expiry_service import expire_old_pending_events
        _launch(expire_old_pending_events(), name="expiry-worker")
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

    logger.info("🛑 Buykori AdSync বন্ধ হচ্ছে...")
    await engine.dispose()


# ─── FastAPI App (ORJSONResponse = 2-3x faster JSON serialization) ────────
app = FastAPI(
    title="Buykori AdSync",
    description="Multi-tenant ad tracking and conversion sync platform",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
    default_response_class=ORJSONResponse,  # 🚀 orjson = C-based, 2-3x faster!
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS,
)

# ─── Redirect Middleware (Heroku -> Custom Domain) ───────────────────────────
class HerokuRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.url.hostname or ""
        if host in {"buykori.app", "www.buykori.app"} and request.url.path.startswith("/client"):
            return RedirectResponse(url="https://client.buykori.app", status_code=308)
        if host.endswith(".herokuapp.com"):
            target_domain = os.getenv("PRIMARY_DOMAIN", "api.buykori.app")
            url = request.url.replace(hostname=target_domain)
            # Use 308 (Permanent Redirect) instead of 301 to preserve HTTP method (POST)
            return RedirectResponse(url=str(url), status_code=308)
        return await call_next(request)

app.add_middleware(HerokuRedirectMiddleware)

# ─── CORS — Multi-Tenant Tracker: allow_origins=["*"] ইচ্ছাকৃত ─────────────
# ব্রাউজার ট্র্যাকার (t.js) যেকোনো ক্লায়েন্ট ওয়েবসাইট থেকে cross-origin request পাঠায়।
# Deploy-time-এ সব ক্লায়েন্ট ডোমেইন জানা সম্ভব নয়, তাই CORS open রাখা হয়েছে।
# প্রকৃত নিরাপত্তা → per-client domain whitelisting (events.py ও tracker.py-তে enforce হয়)।
# Client Portal same-origin cookie ব্যবহার করে; public tracker CORS-এ credentials লাগে না।
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=[
        "X-API-Key",
        "X-Admin-API-Key",
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
app.include_router(client_auth_router, prefix="/api/v1", tags=["Client Auth"])

from app.routers.plugin import router as plugin_router
app.include_router(plugin_router, prefix="/api/v1", tags=["Plugin"])

from app.routers.webhook import router as webhook_router
app.include_router(webhook_router, prefix="/api/v1", tags=["Webhook"])

from app.routers.client_health import router as client_health_router
app.include_router(client_health_router, prefix="/api/v1", tags=["Client Health"])


# ─── Health Check ─────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def marketing_home():
    import os
    site_path = os.path.join(os.path.dirname(__file__), "templates", "site.html")
    with open(site_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/status", tags=["Health"])
async def health_check():
    return {
        "status": "running",
        "service": "Buykori AdSync",
        "version": "1.1.0",
        "message": "🔥 Buykori AdSync চলছে!",
    }
