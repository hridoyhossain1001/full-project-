import logging
import uuid
from typing import Dict, Any, List

from app.services.capi_service import get_http_client
from app.security import decrypt_token

logger = logging.getLogger(__name__)


def extract_ga4_client_id(cookies: dict) -> str:
    """Extract client_id from _ga cookie or generate a random one."""
    ga_cookie = cookies.get("_ga")
    if ga_cookie:
        # Example _ga cookie format: GA1.1.123456789.123456789
        parts = ga_cookie.split('.')
        if len(parts) >= 4:
            return f"{parts[-2]}.{parts[-1]}"
    
    # Fallback to a random UUID if not found
    return str(uuid.uuid4())

def map_event_to_ga4(event_name: str) -> str:
    """Map Facebook standard events to GA4 standard events."""
    mapping = {
        "PageView": "page_view",
        "ViewContent": "view_item",
        "Search": "search",
        "AddToCart": "add_to_cart",
        "InitiateCheckout": "begin_checkout",
        "AddPaymentInfo": "add_payment_info",
        "Purchase": "purchase",
        "Lead": "generate_lead",
        "CompleteRegistration": "sign_up",
        "Contact": "contact",
    }
    return mapping.get(event_name, event_name.lower().replace(' ', '_'))

async def send_to_ga4(events: List[Dict[str, Any]], measurement_id: str, api_secret: str, cookies: dict, ip_address: str, user_agent: str):
    """
    Send events to GA4 via Measurement Protocol.
    Uses the shared persistent HTTP client from capi_service.
    """
    if not measurement_id or not api_secret:
        return

    decrypted_secret = decrypt_token(api_secret)
    url = f"https://www.google-analytics.com/mp/collect?measurement_id={measurement_id}&api_secret={decrypted_secret}"
    client_id = extract_ga4_client_id(cookies)
    
    ga4_events = []
    
    for evt in events:
        fb_event_name = evt.get("event_name", "")
        ga4_event_name = map_event_to_ga4(fb_event_name)
        
        # Build GA4 parameters
        params = {}
        
        # Add basic info
        if evt.get("event_source_url"):
            params["page_location"] = evt.get("event_source_url")
            
        custom_data = evt.get("custom_data", {})
        if custom_data:
            if "value" in custom_data:
                params["value"] = float(custom_data["value"])
            if "currency" in custom_data:
                params["currency"] = custom_data["currency"]
            if "content_ids" in custom_data:
                params["items"] = [{"item_id": i} for i in custom_data["content_ids"]]
                
        # Handle User Data for User Properties
        user_data = evt.get("user_data", {})
        user_properties = {}
        if user_data.get("ct"):
            user_properties["city"] = {"value": user_data["ct"]}
        if user_data.get("country"):
            user_properties["country"] = {"value": user_data["country"]}
            
        # Optional: transaction_id for Purchase
        if ga4_event_name == "purchase" and evt.get("event_id"):
            params["transaction_id"] = evt["event_id"]
            
        ga4_event = {
            "name": ga4_event_name,
            "params": params
        }
        ga4_events.append(ga4_event)
        
    if not ga4_events:
        return

    payload = {
        "client_id": client_id,
        "events": ga4_events
    }
    
    try:
        http_client = await get_http_client()
        response = await http_client.post(url, json=payload)
        # GA4 Measurement Protocol always returns 2xx even if invalid, unless request is malformed
        if response.status_code >= 400:
            logger.error(f"GA4 error: {response.text}")
            return {"ok": False, "status_code": response.status_code, "error": response.text[:500]}
        return {"ok": True, "status_code": response.status_code}
    except Exception as e:
        logger.error(f"Failed to send to GA4: {e}")
        return {"ok": False, "error": str(e)}
