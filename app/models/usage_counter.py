"""
Usage Counter — PostgreSQL-backed rate limit ও daily quota tracking।
সব worker থেকে shared counter, atomic increment দিয়ে।
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class UsageCounter(Base):
    """প্রতি ক্লায়েন্টের per-minute rate ও daily quota ট্র্যাক করে"""
    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("client_id", "window_key", name="uq_client_window"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    window_key = Column(String, nullable=False)   # "rate:2026-05-06T01:13" বা "daily:2026-05-06"
    count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
