import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.schemas.event import EventsPayload, EventsResponse
from app.dependencies import get_current_client
from app.services.capi_service import send_to_facebook
from app.models.client import Client

logger = logging.getLogger(__name__)

# রেট লিমিটার ইনিশিয়ালাইজ করা
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

@router.post(
    "/events",
    response_model=EventsResponse,
    summary="Facebook CAPI Events Endpoint",
)
@limiter.limit("5000/minute", key_func=lambda r: r.headers.get("X-API-Key") or "unknown")
async def receive_events(
    request: Request,
    payload: EventsPayload,
    client: Client = Depends(get_current_client),
):
    """
    ক্লায়েন্টের API Key ভেরিফাই করে Facebook CAPI-তে ইভেন্ট ফরওয়ার্ড করে।
    """
    if not payload.data:
        raise HTTPException(status_code=400, detail="ইভেন্ট ডাটা খালি!")

    try:
        # CAPI সার্ভিসে ডাটা পাঠানো
        result = await send_to_facebook(client, payload.data)
        
        return EventsResponse(
            status="success",
            events_received=len(payload.data),
            message="সফলভাবে Facebook-এ পাঠানো হয়েছে"
        )
        
    except Exception as e:
        logger.error(f"Client {client.name} | Error: {str(e)}")
        raise HTTPException(
            status_code=502, 
            detail="Facebook API তে সমস্যা"
        )
