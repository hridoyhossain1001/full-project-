"""Fast Redis-backed ingest helpers for the /events hot path."""
import json
import os
from datetime import datetime, timezone

from fastapi import HTTPException

from app.services.redis_pool import get_redis


EVENT_INGEST_MODE = os.getenv("EVENT_INGEST_MODE", "db").strip().lower()
REDIS_STREAM_KEY = os.getenv("EVENT_REDIS_STREAM_KEY", "capi:events")
REDIS_STREAM_MAXLEN = int(os.getenv("EVENT_REDIS_STREAM_MAXLEN", "200000"))

_RESERVE_AND_ENQUEUE_LUA = """
local stream_key = KEYS[1]
local client_id = ARGV[1]
local events_data = ARGV[2]
local request_context = ARGV[3]
local usage_reserved = ARGV[4]
local queued_at = ARGV[5]
local maxlen = ARGV[6]
local window_count = tonumber(ARGV[7])
local arg_index = 8
local windows = {}

for i = 1, window_count do
    local key = ARGV[arg_index]
    local increment = tonumber(ARGV[arg_index + 1])
    local ttl = tonumber(ARGV[arg_index + 2])
    local limit = tonumber(ARGV[arg_index + 3])
    arg_index = arg_index + 4

    local count = redis.call("INCRBY", key, increment)
    redis.call("EXPIRE", key, ttl, "NX")
    windows[i] = {key, increment, count, limit}
end

for i = 1, window_count do
    local window = windows[i]
    local count = tonumber(window[3])
    local limit = tonumber(window[4])
    if limit > 0 and count > limit then
        for j = 1, window_count do
            redis.call("DECRBY", windows[j][1], windows[j][2])
        end
        return {"0", tostring(count), tostring(limit)}
    end
end

local stream_id = redis.call(
    "XADD",
    stream_key,
    "MAXLEN",
    "~",
    maxlen,
    "*",
    "client_id",
    client_id,
    "events_data",
    events_data,
    "request_context",
    request_context,
    "usage_reserved",
    usage_reserved,
    "queued_at",
    queued_at
)

return {"1", stream_id}
"""


async def reserve_usage_and_enqueue_stream(
    client,
    *,
    events_data: list[dict],
    request_context: dict,
) -> tuple[bool, dict[str, int]]:
    """
    Reserve usage counters and enqueue a Redis stream message in one Redis round-trip.

    Returns (False, {}) when Redis is unavailable so caller can use the durable DB fallback.
    Raises HTTPException(429) when quota/rate limit is exceeded.
    """
    if EVENT_INGEST_MODE != "redis_stream":
        return False, {}

    r = get_redis()
    if r is None:
        return False, {}

    event_count = len(events_data)
    now = datetime.now(timezone.utc)
    minute_key = f"rate:{now.strftime('%Y-%m-%dT%H:%M')}"
    daily_key = f"daily:{now.strftime('%Y-%m-%d')}"
    monthly_key = f"monthly:{now.strftime('%Y-%m')}"
    reserved_keys = {
        minute_key: event_count,
        daily_key: event_count,
        monthly_key: event_count,
        "_usage_source": "redis",
    }

    rate_limit = getattr(client, "rate_limit", None) or 5000
    daily_quota = getattr(client, "daily_quota", None) or 0
    monthly_limit = getattr(client, "monthly_limit", None) or 0
    windows = [
        (f"usage:{client.id}:{minute_key}", event_count, 65, rate_limit),
        (f"usage:{client.id}:{daily_key}", event_count, 90000, daily_quota),
        (f"usage:{client.id}:{monthly_key}", event_count, 2678400, monthly_limit),
    ]

    args = [
        str(client.id),
        json.dumps(events_data, separators=(",", ":"), default=str),
        json.dumps(request_context or {}, separators=(",", ":"), default=str),
        json.dumps(reserved_keys, separators=(",", ":"), default=str),
        now.isoformat(),
        str(REDIS_STREAM_MAXLEN),
        str(len(windows)),
    ]
    for key, increment, ttl, limit in windows:
        args.extend([key, str(increment), str(ttl), str(limit or 0)])

    try:
        result = await r.eval(_RESERVE_AND_ENQUEUE_LUA, 1, REDIS_STREAM_KEY, *args)
    except Exception:
        return False, {}

    if not result or str(result[0]) != "1":
        count = result[1] if len(result) > 1 else "unknown"
        limit = result[2] if len(result) > 2 else "unknown"
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded! {count}/{limit} events/min",
        )

    return True, reserved_keys
