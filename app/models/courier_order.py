from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base

class CourierOrder(Base):
    __tablename__ = "courier_orders"
    __table_args__ = (
        UniqueConstraint("client_id", "order_id", name="uq_courier_orders_client_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    pending_event_id = Column(Integer, ForeignKey("pending_events.id", ondelete="SET NULL"), nullable=True)
    
    order_id = Column(String(255), nullable=False)                         # WooCommerce/Website order ID
    courier_provider = Column(String(50), nullable=False)                 # 'pathao' / 'steadfast'
    courier_order_id = Column(String(255), nullable=True, index=True)                 # Courier-side order ID
    courier_tracking_id = Column(String(255), nullable=True, index=True)              # Tracking code
    courier_status = Column(String(100), default="pending", nullable=False, index=True) # pending/picked/in_transit/delivered/returned
    
    recipient_name = Column(String(255), nullable=True)
    recipient_phone = Column(String(50), nullable=True)
    recipient_address = Column(String, nullable=True)
    
    cod_amount = Column(Float, default=0.0)
    delivery_charge = Column(Float, default=0.0)
    status_history = Column(JSON, nullable=True)                         # Historical status changes (JSON list)
    purchase_event_sent = Column(Boolean, default=False, nullable=False) # True if Facebook CAPI Purchase event is sent
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
