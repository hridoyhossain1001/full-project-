import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.database import engine, Base
from app.routers.events import router as events_router
from app.routers.admin import router as admin_router
from app.routers.monitoring import router as monitoring_router
from app.limiter import limiter

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ ডাটাবেস সংযোগ সফল।")

    # 🔄 Start Retry Service in background (Web Process-এর ভেতরেই চলবে, আলাদা বাজেট লাগবে না)
    import asyncio
    from app.services.retry_service import retry_failed_events
    asyncio.create_task(retry_failed_events())
    logger.info("⚙️  Background Retry Service স্টার্ট হয়েছে (Web Process)।")

    yield

    # Shutdown — cleanup
    # 🔒 HTTP client বন্ধ করো
    from app.services.capi_service import close_http_client
    await close_http_client()

    logger.info("🛑 CAPI Gateway বন্ধ হচ্ছে...")
    await engine.dispose()


# ─── FastAPI App (ORJSONResponse = 2-3x faster JSON serialization) ────────
app = FastAPI(
    title="CAPI Gateway",
    description="Multi-tenant Facebook Conversion API Gateway — Server-Side Tracking as a Service",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",         # Swagger UI
    redoc_url="/redoc",
    default_response_class=ORJSONResponse,  # 🚀 orjson = C-based, 2-3x faster!
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS — ক্লায়েন্ট ওয়েবসাইট থেকে ইভেন্ট পাঠাতে দরকার ─────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # যেকোনো ক্লায়েন্ট ওয়েবসাইট থেকে রিকোয়েস্ট আসতে পারে
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(events_router, prefix="/api/v1", tags=["Events"])
app.include_router(admin_router,  prefix="/api/v1", tags=["Admin"])
app.include_router(monitoring_router, prefix="/api/v1", tags=["Monitoring"])


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status": "running",
        "service": "CAPI Gateway",
        "version": "1.1.0",
        "message": "🔥 Server-Side Tracking Gateway চলছে!",
    }
