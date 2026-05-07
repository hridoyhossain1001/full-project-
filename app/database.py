import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Heroku দেয় DATABASE_URL যেটা postgres:// দিয়ে শুরু হয়
# SQLAlchemy async-এর জন্য postgresql+asyncpg:// লাগে, তাই replace করছি
raw_url = os.getenv("DATABASE_URL", "")
if not raw_url:
    raise RuntimeError("⛔ DATABASE_URL environment variable is required!")

if raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif raw_url.startswith("postgresql://"):
    raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL = raw_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,          # 2 workers × 5 = 10 base connections
    max_overflow=5,       # 2 workers × 5 = 10 overflow, total max = 20 (Heroku limit)
    pool_recycle=300,     # Recycle stale connections every 5 min
    pool_pre_ping=True,   # Dead connection auto-detect — avoids "connection reset" errors
    pool_timeout=10,      # Max 10s wait for a connection from pool
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
