from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


class EventOutbox(Base):
    """Durable queue for accepted events waiting to be sent to downstream APIs."""

    __tablename__ = "event_outbox"
    __table_args__ = (
        Index("ix_event_outbox_claim", "status", "next_attempt_at", "created_at"),
        Index("ix_event_outbox_client_status", "client_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_payload = Column(JSON, nullable=False)
    request_context = Column(JSON, nullable=True)
    usage_reserved = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="queued", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=8)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String, nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
