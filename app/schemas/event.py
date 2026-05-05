from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class UserData(BaseModel):
    """Facebook CAPI User Data - সব ফিল্ড optional, যতবেশি দেওয়া যায় ততো ভালো match হয়"""
    em: Optional[List[str]] = None        # hashed email
    ph: Optional[List[str]] = None        # hashed phone
    fn: Optional[List[str]] = None        # hashed first name
    ln: Optional[List[str]] = None        # hashed last name
    ct: Optional[List[str]] = None        # hashed city
    st: Optional[List[str]] = None        # hashed state
    zp: Optional[List[str]] = None        # hashed zip
    country: Optional[List[str]] = None   # hashed country
    external_id: Optional[List[str]] = None
    client_ip_address: Optional[str] = None
    client_user_agent: Optional[str] = None
    fbc: Optional[str] = None             # Facebook click ID (_fbc cookie)
    fbp: Optional[str] = None             # Facebook browser ID (_fbp cookie)


class CustomData(BaseModel):
    """Purchase, AddToCart ইত্যাদির জন্য custom data"""
    value: Optional[float] = None
    currency: Optional[str] = None
    content_ids: Optional[List[str]] = None
    content_type: Optional[str] = None
    order_id: Optional[str] = None
    num_items: Optional[int] = None


class EventData(BaseModel):
    """একটি ইভেন্টের সম্পূর্ণ তথ্য"""
    event_name: str                        # PageView, Purchase, AddToCart, etc.
    event_time: int                        # Unix timestamp
    action_source: str = "website"
    event_id: Optional[str] = None        # Deduplication এর জন্য (খুবই জরুরি!)
    event_source_url: Optional[str] = None
    user_data: UserData
    custom_data: Optional[CustomData] = None


class EventsPayload(BaseModel):
    """API-তে আসা মূল payload"""
    data: List[EventData]


class EventsResponse(BaseModel):
    status: str
    events_received: int
    message: str
