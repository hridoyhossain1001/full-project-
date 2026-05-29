import hashlib
import re
from pydantic import BaseModel, model_validator
from typing import List, Dict, Any, Optional

def _clean_and_hash(val: str, field: str) -> str:
    """Normalize and hash PII data according to Facebook CAPI rules."""
    if not isinstance(val, str) or not val.strip():
        return val

    val = val.strip()

    # Check if already SHA256 hashed
    if re.match(r'^[a-f0-9]{64}$', val):
        return val

    # Normalization
    if field == 'ph':
        # Remove non-numeric characters
        val = re.sub(r'[^0-9]', '', val)

        # Bangladesh E.164 normalization:
        # 01XXXXXXXXX (11 digits, starts with 01) → 8801XXXXXXXXX
        # 1XXXXXXXXX  (10 digits, starts with 1)  → 8801XXXXXXXXX
        # 8801XXXXXXXXX (13 digits, already E.164) → keep as-is
        if len(val) == 11 and val.startswith('01'):
            val = '88' + val
        elif len(val) == 10 and val.startswith('1'):
            val = '880' + val
        elif not val.startswith('880') and not val.startswith('0'):
            # Non-BD numbers: strip leading zeros (original behavior)
            val = val.lstrip('0')
    else:
        val = val.lower()
        if field in ('fn', 'ln', 'ct'):
            # Remove punctuation (keep letters and spaces)
            val = re.sub(r'[^\w\s]', '', val)

    return hashlib.sha256(val.encode('utf-8')).hexdigest()

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
    ttp: Optional[str] = None             # TikTok browser ID (_ttp cookie)
    ttclid: Optional[str] = None          # TikTok click ID

    @model_validator(mode='before')
    @classmethod
    def auto_hash_pii(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        hashable_fields = ['em', 'ph', 'fn', 'ln', 'ct', 'st', 'zp', 'country']
        # Note: external_id is NOT hashed — Meta recommends hashing only if it contains PII.
        # Buykori uses auto-generated visitor IDs, not PII, so hashing reduces match quality.

        for field in hashable_fields:
            if field in data and data[field] is not None:
                val = data[field]
                # If a single string is provided, wrap it in a list
                if isinstance(val, str):
                    val = [val]

                # Clean and hash each item in the list
                if isinstance(val, list):
                    cleaned_list = []
                    for item in val:
                        if isinstance(item, str):
                            cleaned_list.append(_clean_and_hash(item, field))
                        else:
                            cleaned_list.append(item)
                    data[field] = cleaned_list

        return data


class CustomData(BaseModel):
    """Purchase, AddToCart ইত্যাদির জন্য custom data"""
    model_config = {"extra": "allow"}
    value: Optional[float] = None
    currency: Optional[str] = None
    content_ids: Optional[List[str]] = None
    content_type: Optional[str] = None
    order_id: Optional[str] = None
    num_items: Optional[int] = None
    contents: Optional[List[Dict[str, Any]]] = None


class EventData(BaseModel):
    """একটি ইভেন্টের সম্পূর্ণ তথ্য"""
    event_name: str                        # PageView, Purchase, AddToCart, etc.
    event_time: int                        # Unix timestamp
    action_source: str = "website"
    event_id: Optional[str] = None        # Deduplication এর জন্য (খুবই জরুরি!)
    event_source_url: Optional[str] = None
    user_data: Optional[UserData] = None
    custom_data: Optional[CustomData] = None
    raw_order_data: Optional[Dict[str, Any]] = None  # internal courier data, never sent to ad platforms
    emq_score: Optional[float] = None      # Event Match Quality Score (internal use)


class EventsPayload(BaseModel):
    """API-তে আসা মূল payload"""
    data: List[EventData]


class EventsResponse(BaseModel):
    status: str
    events_received: int
    message: str
