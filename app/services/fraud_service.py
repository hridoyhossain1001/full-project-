import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, Any, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pending_event import PendingEvent
from app.schemas.event import EventData, UserData, _clean_and_hash
from app.services.geoip_service import get_location_data

logger = logging.getLogger(__name__)

# ─── Popular Disposable / Temporary Email Domains ───────────────────────────
DISPOSABLE_DOMAINS = {
    "tempmail.com", "temp-mail.org", "10minutemail.com", "yopmail.com",
    "mailinator.com", "dispostable.com", "guerrillamail.com", "sharklasers.com",
    "getairmail.com", "maildrop.cc", "throwawaymail.com", "tempmailaddress.com",
    "burnermail.io", "tempmail.net", "fakeinbox.com", "crazymailing.com",
    "mailnesia.com", "mailcatch.com", "trashmail.com", "tempail.com"
}

# ─── Gibberish Key Sequences (common spam keyboard sequences) ───────────────
GIBBERISH_PATTERNS = [
    r"asdfgh", r"qwerty", r"zxcvbn", r"12345", r"qwer", r"asdf", r"zxcv",
    r"uiop", r"hjkl", r"bnm"
]
_GIBBERISH_REGEX = re.compile("|".join(GIBBERISH_PATTERNS), re.IGNORECASE)


def is_disposable_email(email_domain: str) -> bool:
    """
    ইমেইল ডোমেইনটি টেম্পোরারি বা ওয়ান-টাইম ইমেইল কিনা তা পরীক্ষা করে।
    """
    if not email_domain:
        return False
    domain = email_domain.strip().lower()
    return domain in DISPOSABLE_DOMAINS


def is_gibberish(name: str) -> bool:
    """
    নামটি কিবোর্ডের র্যান্ডম টেক্সট (যেমন: asdfgh, qwerty) বা ফেক প্যাটার্ন কিনা সনাক্ত করে।
    """
    if not name:
        return False
    name_clean = name.strip()
    
    # ১. দৈর্ঘ্য খুব ছোট হলে (যেমন: 1, 2 অক্ষরের নাম)
    if len(name_clean) < 3:
        return True
        
    # ২. নাম যদি শুধুমাত্র সংখ্যা বা র্যান্ডম সিম্বল হয়
    if name_clean.isdigit():
        return True
        
    # ৩. একই অক্ষর ৩ বারের বেশি পুনরাবৃত্তি হলে (যেমন: "aaaa", "bbbb")
    if re.search(r"(.)\1{3,}", name_clean.lower()):
        return True
        
    # ৪. কিবোর্ডের স্ট্যান্ডার্ড সিকোয়েন্স থাকলে (যেমন: "asdf", "qwerty")
    if _GIBBERISH_REGEX.search(name_clean):
        return True
        
    # ৫. কোনো কনসোনেন্ট-অনলি বা অতি কম ভাওয়েল চেক (ইংরেজী নামের ক্ষেত্রে)
    # ইংরেজি অক্ষরে লেখা নামের সাইজ > ৪ হলে এবং কোনো ভাওয়েল (a, e, i, o, u, y) না থাকলে
    if len(name_clean) > 4 and name_clean.isalpha():
        vowels = set("aeiouy")
        if not any(char in vowels for char in name_clean.lower()):
            return True
            
    return False


def check_ip_location_mismatch(client_ip: str, user_data: UserData) -> bool:
    """
    GeoIP কান্ট্রি এবং কাস্টমারের বিলিং কান্ট্রি মেলেনি কিনা তা চেক করে।
    hashed billing country-র সাথে GeoIP কান্ট্রির SHA-256 তুলনা করা হয়।
    """
    if not client_ip or not user_data or not user_data.country:
        return False

    # GeoIP দিয়ে আইপির লোকেশন বের করো
    loc = get_location_data(client_ip)
    loc_country = loc.get("country")
    if not loc_country:
        return False  # GeoIP ডাটা না পাওয়া গেলে mismatch ধরা হবে না

    # GeoIP কান্ট্রি কোডকে Facebook CAPI ফরম্যাটে SHA-256 হ্যাশ করো
    hashed_loc_country = _clean_and_hash(loc_country, "country")

    # কাস্টমারের কান্ট্রি লিস্টে আমাদের হ্যাশ করা GeoIP কান্ট্রি আছে কিনা চেক করো
    # matching_country পাওয়া গেলে অমিল নেই (False), না পাওয়া গেলে mismatch (True)
    return hashed_loc_country not in user_data.country


async def check_velocity(
    db: AsyncSession,
    client_id: int,
    client_ip: str,
    phone_hashes: List[str]
) -> bool:
    """
    Velocity check: একই IP বা একই ফোন নম্বর থেকে গত ১০ মিনিটে একাধিক pending Purchase অর্ডার করা হয়েছে কিনা।
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    
    # গত ১০ মিনিটের সকল pending events কুয়েরি করো
    result = await db.execute(
        select(PendingEvent).where(
            and_(
                PendingEvent.client_id == client_id,
                PendingEvent.status == "pending",
                PendingEvent.created_at >= cutoff
            )
        )
    )
    pending_events = result.scalars().all()

    # Include the incoming order in the threshold, so the 3rd matching order in
    # the window is flagged instead of waiting until a 4th order arrives.
    ip_count = 1 if client_ip else 0
    phone_count = 1 if phone_hashes else 0
    
    phone_hash_set = set(phone_hashes or [])

    for pe in pending_events:
        event_data = pe.event_data or {}
        ud = event_data.get("user_data", {}) or {}
        
        # IP checking
        pe_ip = ud.get("client_ip_address")
        if pe_ip and client_ip and pe_ip == client_ip:
            ip_count += 1
            
        # Phone checking
        pe_ph = ud.get("ph") or []
        if isinstance(pe_ph, list):
            for ph in pe_ph:
                if ph in phone_hash_set:
                    phone_count += 1
                    break

    # ৩ বা তার বেশি অর্ডার সাবমিট করলে ভেলোসিটি ট্রিগার হবে
    return (ip_count >= 3) or (phone_count >= 3)


async def calculate_fraud_score(
    db: AsyncSession,
    client_id: int,
    event: EventData,
    client_ip: str
) -> Tuple[int, Dict[str, bool]]:
    """
    একটি incoming Purchase ইভেন্টের Fraud Risk Score (০-১০০) হিসাব করে।
    রিটার্ন করে: (score, details)
    """
    score = 0
    details = {
        "ip_mismatch": False,
        "disposable_email": False,
        "velocity_limit": False,
        "gibberish_name": False
    }

    if not event or not event.user_data:
        return score, details

    user_data = event.user_data
    custom_data = event.custom_data or getattr(event, "custom_data", None)
    custom_dict = custom_data.model_dump(exclude_none=True) if hasattr(custom_data, "model_dump") else (custom_data or {})

    # ─── Heuristic 1: IP-Location Mismatch (+25) ─────────────────────────────
    if check_ip_location_mismatch(client_ip, user_data):
        score += 25
        details["ip_mismatch"] = True

    # ─── Heuristic 2: Disposable Email Check (+30) ───────────────────────────
    # unhashed domain from custom_data (e.g. 'email_domain' or 'billing_email_domain')
    email_domain = custom_dict.get("email_domain") or custom_dict.get("billing_email_domain")
    if email_domain and is_disposable_email(email_domain):
        score += 30
        details["disposable_email"] = True

    # ─── Heuristic 3: Velocity Limiting (+35) ────────────────────────────────
    phone_hashes = user_data.ph or []
    if await check_velocity(db, client_id, client_ip, phone_hashes):
        score += 35
        details["velocity_limit"] = True

    # ─── Heuristic 4: Gibberish Name Check (+20) ─────────────────────────────
    # unhashed raw first name from custom_data
    raw_first_name = custom_dict.get("raw_first_name") or custom_dict.get("billing_first_name_raw")
    if raw_first_name and is_gibberish(raw_first_name):
        score += 20
        details["gibberish_name"] = True

    # Ensure score stays in [0, 100] range
    score = min(score, 100)

    logger.info(f"[Client #{client_id}] Fraud engine completed. Score: {score}/100. Details: {details}")

    return score, details
