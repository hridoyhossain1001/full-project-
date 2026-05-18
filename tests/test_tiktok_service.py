import os
from types import SimpleNamespace

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-api-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("ENCRYPTION_KEY", "ZFhnf1szwemka8kBbH9jPTC7oKBRTEv0EqWt1J8AD0M=")

from app.schemas.event import EventData
from app.services.tiktok_service import _build_tiktok_payload, _map_event_name


def test_tiktok_pageview_does_not_become_viewcontent():
    assert _map_event_name("PageView") == "PageView"


def test_tiktok_purchase_uses_current_standard_event_name():
    assert _map_event_name("Purchase") == "Purchase"


def test_tiktok_viewcontent_keeps_product_content_ids():
    client = SimpleNamespace(tiktok_pixel_id="TT_PIXEL", tiktok_test_event_code=None)
    event = EventData(
        event_name="ViewContent",
        event_time=1710000000,
        event_id="view-123",
        event_source_url="https://example.com/product/123",
        custom_data={
            "content_ids": ["123"],
            "content_type": "product",
            "value": 1200,
            "currency": "BDT",
        },
    )

    payload = _build_tiktok_payload(client, [event])

    assert payload["data"][0]["event"] == "ViewContent"
    assert payload["data"][0]["properties"]["contents"] == [
        {"content_id": "123", "content_type": "product"}
    ]


def test_tiktok_payload_includes_ttp_and_ttclid():
    client = SimpleNamespace(tiktok_pixel_id="TT_PIXEL", tiktok_test_event_code=None)
    event = EventData(
        event_name="PageView",
        event_time=1710000000,
        event_id="page-123",
        event_source_url="https://example.com/?ttclid=click-123",
        user_data={
            "client_user_agent": "Mozilla/5.0",
            "client_ip_address": "203.0.113.10",
            "ttp": "ttp-cookie",
            "ttclid": "click-123",
        },
    )

    payload = _build_tiktok_payload(client, [event])
    context = payload["data"][0]["context"]

    assert context["user"]["ttp"] == "ttp-cookie"
    assert context["ad"]["callback"] == "click-123"
