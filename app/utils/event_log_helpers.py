"""
Shared EventLog helper — builds kwargs dict for creating EventLog rows.
Used by events.py router and event_worker.py service to avoid duplication.
"""

from app.services.event_quality import event_signal_flags


def build_event_log_kwargs(
    client_id: int,
    event_data,
    status: str,
    ip_address: str | None,
    **extra,
) -> dict:
    """
    EventLog row তৈরির জন্য kwargs dict build করে।
    event_data একটি dict (model_dump output) বা Pydantic model হতে পারে।
    """
    # Enforce Pydantic model check and convert to dict
    if hasattr(event_data, "model_dump"):
        event_data = event_data.model_dump()
    elif hasattr(event_data, "dict"):
        event_data = event_data.dict()

    if not isinstance(event_data, dict):
        event_data = {}

    custom_data = event_data.get("custom_data") or {}
    utm_source = custom_data.get("utm_source")

    # Fix the boolean float casting bug that converts True to 1.0 / False to 0.0
    val = custom_data.get("value")
    if isinstance(val, bool):
        value = None
    else:
        try:
            value = float(val) if val is not None else None
        except (TypeError, ValueError):
            value = None

    campaign_source = custom_data.get("campaign_source") or utm_source
    return {
        "client_id": client_id,
        "event_name": event_data.get("event_name") or "unknown",
        "event_id": event_data.get("event_id"),
        "event_count": 1,
        "status": status,
        "ip_address": ip_address,
        "emq_score": event_data.get("emq_score"),
        "value": value,
        "currency": custom_data.get("currency"),
        "campaign_source": campaign_source,
        "utm_source": utm_source,
        "utm_medium": custom_data.get("utm_medium"),
        "utm_campaign": custom_data.get("utm_campaign"),
        "utm_content": custom_data.get("utm_content"),
        "utm_term": custom_data.get("utm_term"),
        **event_signal_flags(event_data),
        **extra,
    }
