from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.sql import func
from app.database import Base


class FailedEvent(Base):
    """ব্যর্থ ইভেন্ট — পরবর্তীতে retry করা হবে"""
    __tablename__ = "failed_events"
    __table_args__ = (
        Index("ix_failed_events_retry_claim", "status", "retry_count", "last_retry_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_payload = Column(JSON, nullable=False)          # সম্পূর্ণ ইভেন্ট ডাটা
    error_message = Column(Text, nullable=True)           # ব্যর্থতার কারণ
    retry_count = Column(Integer, default=0)              # কতবার retry হয়েছে
    max_retries = Column(Integer, default=5)              # সর্বোচ্চ কতবার retry হবে
    status = Column(String, default="pending", index=True)  # pending / retrying / success / dead
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_retry_at = Column(DateTime(timezone=True), nullable=True)
