from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class ClientUser(Base):
    __tablename__ = "client_users"
    __table_args__ = (
        # Multi-tenancy: একই ইমেইল ভিন্ন ক্লায়েন্ট কোম্পানিতে ব্যবহার করা যাবে
        # Global unique=True সরানো হয়েছে — SaaS-এ এটি ভুল ছিল
        UniqueConstraint("client_id", "email", name="uq_client_users_client_email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=True)
    notification_email = Column(String(255), nullable=True)
    role = Column(String(40), nullable=False, default="owner")
    is_active = Column(Boolean, nullable=False, default=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
