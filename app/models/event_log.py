from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.sql import func
from app.database import Base


class EventLog(Base):
    """প্রতিটি ইভেন্ট কলের লগ — ডিবাগিং, অ্যানালিটিক্স ও বিলিং-এর জন্য"""
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    event_name = Column(String, nullable=False)          # PageView, Purchase, etc.
    event_id = Column(String, nullable=True, index=True) # Deduplication key (client_id + event_id = unique)
    event_count = Column(Integer, default=1)              # একবারে কয়টি ইভেন্ট পাঠানো হয়েছে
    status = Column(String, nullable=False, default="success")  # success / failed
    fb_response = Column(Text, nullable=True)             # Facebook-এর response JSON
    error_message = Column(Text, nullable=True)           # Error হলে message
    ip_address = Column(String, nullable=True)            # রিকোয়েস্টের IP
    emq_score = Column(Float, nullable=True)              # Event Match Quality Score (0-10)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
