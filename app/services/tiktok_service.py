"""
TikTok Events API Service — Facebook CAPI-র পাশাপাশি TikTok-এও ইভেন্ট ফরওয়ার্ড করে।

TikTok Events API v1.3 ব্যবহার করে।
ক্লায়েন্টের tiktok_pixel_id ও tiktok_access_token থাকলেই কাজ করবে।
"""

import logging
from typing import List

from app.schemas.event import EventData
from app.security import decrypt_token
from app.services.capi_service import get_http_client

logger = logging.getLogger(__name__)

TIKTOK_API_URL = "https://business-api.tiktok.com/open_api/v1.3/event/track/"


def _map_event_name(fb_event_name: str) -> str:
    """Facebook event name কে TikTok-এর সমতুল্য ইভেন্টে কনভার্ট করে।"""
    mapping = {
        "PageView": "ViewContent",
        "ViewContent": "ViewContent",
        "AddToCart": "AddToCart",
        "InitiateCheckout": "InitiateCheckout",
        "AddPaymentInfo": "AddPaymentInfo",
        "Purchase": "PlaceAnOrder",
        "CompletePayment": "CompletePayment",
        "Lead": "SubmitForm",
        "Contact": "Contact",
        "Search": "Search",
        "Subscribe": "Subscribe",
        "CompleteRegistration": "CompleteRegistration",
    }
    return mapping.get(fb_event_name, fb_event_name)


def _build_tiktok_payload(client, events: List[EventData]) -> dict:
    """Facebook EventData লিস্ট থেকে TikTok Events API-র payload বানায়।"""
    tiktok_events = []

    for event in events:
        tt_event = {
            "event": _map_event_name(event.event_name),
            "event_id": event.event_id or "",
            "event_time": int(event.event_time),
            "page": {
                "url": event.event_source_url or "",
            },
        }

        # User data mapping
        if event.user_data:
            ud = event.user_data
            context = {
                "user_agent": ud.client_user_agent or "",
                "ip": ud.client_ip_address or "",
            }
            user = {}
            if ud.em:
                user["email"] = ud.em[0] if ud.em else None
            if ud.ph:
                user["phone_number"] = ud.ph[0] if ud.ph else None
            if ud.external_id:
                user["external_id"] = ud.external_id[0] if ud.external_id else None

            # TikTok click ID (ttclid) from fbc if available
            # Note: TikTok uses ttclid, not fbc. But we pass what we have.

            context["user"] = user
            tt_event["context"] = context

        # Custom/Properties data
        if event.custom_data:
            cd = event.custom_data
            properties = {}
            if cd.value is not None:
                properties["value"] = cd.value
            if cd.currency:
                properties["currency"] = cd.currency
            if cd.content_ids:
                properties["contents"] = [
                    {"content_id": cid, "content_type": cd.content_type or "product"}
                    for cid in cd.content_ids
                ]
            if cd.order_id:
                properties["order_id"] = cd.order_id
            if cd.num_items is not None:
                properties["num_items"] = cd.num_items
            if properties:
                tt_event["properties"] = properties

        tiktok_events.append(tt_event)

    return {
        "pixel_code": client.tiktok_pixel_id,
        "event_source": "web",
        "event_source_id": client.tiktok_pixel_id,
        "data": tiktok_events,
    }


async def send_to_tiktok(client, events: List[EventData]) -> dict | None:
    """
    TikTok Events API-তে ইভেন্ট পাঠায়।
    ক্লায়েন্টের TikTok credentials না থাকলে None রিটার্ন করে (skip)।
    """
    if not client.tiktok_pixel_id or not client.tiktok_access_token:
        return None  # TikTok কনফিগার করা নেই — skip

    payload = _build_tiktok_payload(client, events)

    try:
        http_client = await get_http_client()
        response = await http_client.post(
            TIKTOK_API_URL,
            json=payload,
            headers={
                "Access-Token": decrypt_token(client.tiktok_access_token),
                "Content-Type": "application/json",
            },
        )
        result = response.json()

        if response.status_code == 200 and result.get("code") == 0:
            logger.info(
                f"[{client.name}] ✅ TikTok: {len(events)} ইভেন্ট সফল। "
                f"Response: {result.get('message', 'OK')}"
            )
        else:
            logger.warning(
                f"[{client.name}] ⚠️ TikTok API Warning: "
                f"Status={response.status_code}, Response={result}"
            )

        return result

    except Exception as e:
        # TikTok ফেইল হলে Facebook-এর সফলতা প্রভাবিত হবে না
        logger.error(f"[{client.name}] ❌ TikTok Error (non-fatal): {e}")
        return None
