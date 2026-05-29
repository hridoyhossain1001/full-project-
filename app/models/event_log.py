from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.sql import func
from app.database import Base


class EventLog(Base):
    """প্রতিটি ইভেন্ট কলের লগ — ডিবাগিং, অ্যানালিটিক্স ও বিলিং-এর জন্য"""
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_name = Column(String, nullable=False, index=True)  # PageView, Purchase, etc.
    event_id = Column(String, nullable=True, index=True)     # Deduplication key (client_id + event_id = unique)
    event_count = Column(Integer, default=1)                 # একবারে কয়টি ইভেন্ট পাঠানো হয়েছে
    status = Column(String, nullable=False, default="success")  # success / failed
    fb_response = Column(Text, nullable=True)                # Facebook-এর response JSON
    error_message = Column(Text, nullable=True)              # Error হলে message
    ip_address = Column(String, nullable=True)               # রিকোয়েস্টের IP
    emq_score = Column(Float, nullable=True)                 # Event Match Quality Score (0-10)
    value = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    campaign_source = Column(String, nullable=True, index=True)
    utm_source = Column(String, nullable=True, index=True)
    utm_medium = Column(String, nullable=True)
    utm_campaign = Column(String, nullable=True, index=True)
    utm_content = Column(String, nullable=True)
    utm_term = Column(String, nullable=True)
    has_content_ids = Column(Boolean, nullable=False, default=False)
    has_contents = Column(Boolean, nullable=False, default=False)
    has_value = Column(Boolean, nullable=False, default=False)
    has_currency = Column(Boolean, nullable=False, default=False)
    has_user_match = Column(Boolean, nullable=False, default=False)
    has_email_phone = Column(Boolean, nullable=False, default=False)
    has_click_id = Column(Boolean, nullable=False, default=False)
    has_event_id = Column(Boolean, nullable=False, default=False)
    has_utm = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    from sqlalchemy import Index
    __table_args__ = (
        Index("ix_event_logs_analytics", "client_id", "event_name", "created_at"),
        Index("ix_event_logs_campaign", "client_id", "utm_source", "utm_campaign", "created_at"),
    )
