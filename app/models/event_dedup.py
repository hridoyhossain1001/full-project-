from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class EventDedup(Base):
    """Event IDs reserved before sending, so concurrent requests cannot double-send."""

    __tablename__ = "event_deduplications"
    __table_args__ = (
        UniqueConstraint("client_id", "event_id", name="uq_event_deduplications_client_event_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
