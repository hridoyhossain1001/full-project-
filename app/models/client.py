import secrets
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)                         # ক্লায়েন্টের নাম
    api_key = Column(String, unique=True, nullable=False,          # অটো-জেনারেটেড API Key
                     default=lambda: secrets.token_urlsafe(32))
    public_key = Column(String, unique=True, nullable=False,       # Browser-safe tracker key
                        default=lambda: secrets.token_urlsafe(24))
    portal_key = Column(String, unique=True, nullable=True)        # Client portal login secret
    pixel_id = Column(String, nullable=False)                      # Facebook Pixel ID
    access_token = Column(String, nullable=False)                  # CAPI Access Token (encrypted)
    test_event_code = Column(String, nullable=True)               # FB Test Event Code (optional)
    is_active = Column(Boolean, default=True)                      # ক্লায়েন্ট অ্যাক্টিভ কিনা
    domain = Column(String, nullable=True)                         # ক্লায়েন্টের ওয়েবসাইট ডোমেইন
    rate_limit = Column(Integer, default=5000)                     # প্রতি মিনিটে সর্বোচ্চ রিকোয়েস্ট
    daily_quota = Column(Integer, default=100000)                  # প্রতিদিন সর্বোচ্চ ইভেন্ট
    # ─── TikTok CAPI Integration ──────────────────────────────────────────
    tiktok_pixel_id = Column(String, nullable=True)               # TikTok Pixel ID (optional)
    tiktok_access_token = Column(String, nullable=True)           # TikTok Access Token (encrypted, optional)
    tiktok_test_event_code = Column(String, nullable=True)        # TikTok Test Event Code (ফেসবুক থেকে আলাদা)
    # ─── GA4 Server-Side Integration ──────────────────────────────────────
    ga4_measurement_id = Column(String, nullable=True)            # GA4 Measurement ID (e.g. G-XXXXX)
    ga4_api_secret = Column(String, nullable=True)                # GA4 API Secret (encrypted)
    # ─── Deferred Purchase ──────────────────────────────────────────────
    deferred_purchase = Column(Boolean, default=False)             # ON হলে Purchase event হোল্ড হবে
    # ─── Webhook (Outbound) ────────────────────────────────────────────
    webhook_url = Column(String, nullable=True)                    # Custom Webhook URL (outbound)
    # ─── Monthly Usage Limit (Rate Limiting Per-Client) ───────────────
    monthly_limit = Column(Integer, default=50000)                  # মাসিক সর্বোচ্চ ইভেন্ট (0 = unlimited)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
