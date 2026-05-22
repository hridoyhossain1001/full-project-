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


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quantity(value) -> int:
    number = _number(value)
    if number is None:
        return 0
    return max(0, int(number))


def _map_event_name(fb_event_name: str) -> str:
    """Facebook event name কে TikTok-এর সমতুল্য ইভেন্টে কনভার্ট করে।"""
    mapping = {
        "PageView": "PageView",
        "ViewContent": "ViewContent",
        "AddToCart": "AddToCart",
        "InitiateCheckout": "InitiateCheckout",
        "AddPaymentInfo": "AddPaymentInfo",
        "Purchase": "Purchase",
        "CompletePayment": "CompletePayment",
        "Lead": "SubmitForm",
        "Contact": "Contact",
        "Search": "Search",
        "Subscribe": "Subscribe",
        "CompleteRegistration": "CompleteRegistration",
    }
    return mapping.get(fb_event_name, fb_event_name)


def _normalize_tiktok_contents(cd) -> list[dict]:
    content_type = cd.content_type or "product"
    raw_contents = getattr(cd, "contents", None) or []
    normalized = []

    for item in raw_contents:
        if not isinstance(item, dict):
            continue

        content_id = item.get("content_id") or item.get("id")
        if not content_id:
            continue

        normalized_item = {
            "content_id": str(content_id),
            "content_type": item.get("content_type") or content_type,
        }

        if item.get("content_name"):
            normalized_item["content_name"] = item.get("content_name")
        if item.get("content_category"):
            normalized_item["content_category"] = item.get("content_category")
        quantity = _quantity(item.get("quantity"))
        if quantity:
            normalized_item["quantity"] = quantity

        price = _number(item.get("price"))
        if price is None:
            price = _number(item.get("item_price"))
        if price is not None:
            normalized_item["price"] = price

        normalized.append(normalized_item)

    if normalized:
        return normalized

    if cd.content_ids:
        return [
            {"content_id": str(cid), "content_type": content_type}
            for cid in cd.content_ids
            if cid
        ]

    return []


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
            if ud.ttp:
                user["ttp"] = ud.ttp
            if ud.ttclid:
                context["ad"] = {"callback": ud.ttclid}

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
            if cd.content_type:
                properties["content_type"] = cd.content_type
            if cd.content_ids:
                properties["content_ids"] = [str(cid) for cid in cd.content_ids if cid]
                if len(properties["content_ids"]) == 1:
                    properties["content_id"] = properties["content_ids"][0]
                properties.setdefault("content_type", cd.content_type or "product")
            contents = _normalize_tiktok_contents(cd)
            if contents:
                properties["contents"] = contents
                total_quantity = sum(_quantity(item.get("quantity")) for item in contents)
                if total_quantity:
                    properties["quantity"] = total_quantity
                if contents[0].get("content_name"):
                    properties["description"] = contents[0]["content_name"]
            if cd.order_id:
                properties["order_id"] = cd.order_id
            if cd.num_items is not None:
                properties["num_items"] = cd.num_items
                properties.setdefault("quantity", cd.num_items)
            if properties:
                tt_event["properties"] = properties

        tiktok_events.append(tt_event)

    payload = {
        "pixel_code": client.tiktok_pixel_id,
        "event_source": "web",
        "event_source_id": client.tiktok_pixel_id,
        "data": tiktok_events,
    }
    
    # TikTok-এর জন্য আলাদা test_event_code ব্যবহার করো
    # tiktok_test_event_code থাকলে সেটা, নাহলে কিছুই না (FB test code TikTok-এ যাবে না)
    tt_test_code = getattr(client, 'tiktok_test_event_code', None)
    if tt_test_code:
        payload["test_event_code"] = tt_test_code

    return payload


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
