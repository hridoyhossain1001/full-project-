from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class PendingEvent(Base):
    """
    Deferred Purchase Events — অর্ডার কনফার্ম না হওয়া পর্যন্ত হোল্ড থাকবে।
    কনফার্ম হলে Facebook-এ পাঠানো হবে, ক্যান্সেল হলে ডিলিট।
    ৭ দিনের বেশি পুরোনো pending events auto-expire হবে।
    """
    __tablename__ = "pending_events"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    order_id = Column(String, nullable=False, index=True)           # "order-12345"
    event_data = Column(JSON, nullable=False)                        # সম্পূর্ণ event payload (user_data সহ)
    status = Column(String, default="pending", index=True)           # pending / confirmed / cancelled / expired
    fraud_score = Column(Integer, nullable=True)                     # Fraud Risk Score (0-100)
    fraud_details = Column(JSON, nullable=True)                      # Heuristics evaluation details JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # একই ক্লায়েন্টের একই order_id duplicate হতে পারবে না
    __table_args__ = (
        UniqueConstraint('client_id', 'order_id', name='uq_client_order'),
    )
