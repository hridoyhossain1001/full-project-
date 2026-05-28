"""
Usage Service — PostgreSQL-backed rate limit ও daily/monthly quota enforcement।

Architecture:
  - check_and_reserve_usage()      → Atomic: check + reserve (counter increment) একসাথে
  - rollback_usage_reservation()   → Send ফেইল হলে reservation undo করে
  - increment_usage_counters_db()  → Legacy: শুধু increment (backward compatibility)

Atomic reserve approach:
  1. Counter atomically increment করে (INSERT ... ON CONFLICT DO UPDATE ... RETURNING)
  2. নতুন count limit-এর বেশি হলে → rollback + 429 error
  3. Facebook send ফেইল হলে → rollback_usage_reservation() দিয়ে counter কমায়

এই approach race condition বন্ধ করে — কারণ increment নিজেই atomic (PostgreSQL guarantee)।
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import engine
from app.models.usage_counter import UsageCounter
from app.services.redis_pool import get_redis

logger = logging.getLogger(__name__)
USAGE_DB_SYNC_IN_REQUEST = os.getenv(
    "USAGE_DB_SYNC_IN_REQUEST",
    "",
).lower() in ("true", "1", "yes")


def _get_redis():
    return get_redis()


async def check_rate_limit_only(client, incoming_event_count: int) -> None:
    """Fast best-effort per-minute rate limit for Redis stream hot paths."""
    rate_limit = getattr(client, "rate_limit", None) or 5000
    r = _get_redis()
    if r is None:
        return

    now = datetime.now(timezone.utc)
    minute_key = f"rate:{now.strftime('%Y-%m-%dT%H:%M')}"
    rkey = f"usage:{client.id}:{minute_key}"
    try:
        pipe = r.pipeline()
        pipe.incrby(rkey, incoming_event_count)
        pipe.expire(rkey, 65, nx=True)
        results = await pipe.execute()
        new_rate = results[0]
        if new_rate > rate_limit:
            await r.decrby(rkey, incoming_event_count)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded! {new_rate}/{rate_limit} events/min",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[{client.name}] Redis rate-limit check failed: {exc}")


async def _atomic_reserve(
    db: AsyncSession,
    client_id: int,
    window_key: str,
    event_count: int,
) -> int:
    """
    Atomically increment a usage counter and return the NEW count.
    PostgreSQL INSERT ... ON CONFLICT DO UPDATE ... RETURNING guarantees atomicity.
    """
    if engine.dialect.name == "postgresql":
        stmt = (
            pg_insert(UsageCounter)
            .values(
                client_id=client_id,
                window_key=window_key,
                count=event_count,
            )
            .on_conflict_do_update(
                constraint="uq_client_window",
                set_={"count": UsageCounter.count + event_count},
            )
            .returning(UsageCounter.count)
        )
        result = await db.execute(stmt)
        return result.scalar()
    else:
        # SQLite fallback (thread-safe fallback checking if row exists and incrementing inside transaction)
        stmt = (
            select(UsageCounter)
            .where(
                UsageCounter.client_id == client_id,
                UsageCounter.window_key == window_key,
            )
            .with_for_update()
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            row.count += event_count
            await db.flush()
            return row.count
        else:
            row = UsageCounter(
                client_id=client_id,
                window_key=window_key,
                count=event_count,
            )
            db.add(row)
            await db.flush()
            return row.count


async def _atomic_rollback(
    db: AsyncSession,
    client_id: int,
    window_key: str,
    event_count: int,
) -> None:
    """
    Counter থেকে event_count বাদ দাও (send ফেইল হলে)।
    """
    stmt = (
        update(UsageCounter)
        .where(
            UsageCounter.client_id == client_id,
            UsageCounter.window_key == window_key,
        )
        .values(count=UsageCounter.count - event_count)
    )
    await db.execute(stmt)


async def check_and_reserve_usage(
    db: AsyncSession,
    client,
    incoming_event_count: int,
) -> dict:
    """
    Atomic check + reserve — race condition মুক্ত!

    Flow:
    1. Counter atomically বাড়ায়
    2. নতুন count > limit হলে rollback + 429
    3. সফল হলে reserved keys dict return করে (rollback-এর জন্য)

    Returns: dict of {window_key: event_count} — rollback-এ ব্যবহার হবে
    """
    now = datetime.now(timezone.utc)
    rate_limit = getattr(client, "rate_limit", None) or 5000
    reserved_keys: dict[str, int] = {}
    minute_key = f"rate:{now.strftime('%Y-%m-%dT%H:%M')}"
    daily_key = f"daily:{now.strftime('%Y-%m-%d')}"
    monthly_key = f"monthly:{now.strftime('%Y-%m')}"
    reservations = [
        (minute_key, incoming_event_count),
        (daily_key, incoming_event_count),
        (monthly_key, incoming_event_count),
    ]

    r = _get_redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            ttl_map = {minute_key: 65, daily_key: 90000, monthly_key: 2678400}
            for window_key, event_count in reservations:
                rkey = f"usage:{client.id}:{window_key}"
                pipe.incrby(rkey, event_count)
                pipe.expire(rkey, ttl_map[window_key], nx=True)
            results = await pipe.execute()

            counts = {}
            counter_results = results[0::2]
            for (window_key, _), new_count in zip(reservations, counter_results):
                counts[window_key] = new_count

            daily_quota = getattr(client, "daily_quota", None)
            monthly_limit = getattr(client, "monthly_limit", None)
            if (
                counts.get(minute_key, 0) > rate_limit
                or (daily_quota and counts.get(daily_key, 0) > daily_quota)
                or (monthly_limit and counts.get(monthly_key, 0) > monthly_limit)
            ):
                pipe = r.pipeline()
                for window_key, event_count in reservations:
                    pipe.decrby(f"usage:{client.id}:{window_key}", event_count)
                await pipe.execute()
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded! {counts.get(minute_key, 0)}/{rate_limit} events/min",
                )

            reserved_keys = {window_key: event_count for window_key, event_count in reservations}
            reserved_keys["_usage_source"] = "redis"
            if not USAGE_DB_SYNC_IN_REQUEST:
                return reserved_keys
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"[{client.name}] Redis usage reserve failed, falling back to DB: {exc}")

    # ─── Per-Minute Rate Limit ─────────────────────────────────────────
    minute_key = f"rate:{now.strftime('%Y-%m-%dT%H:%M')}"
    new_rate = await _atomic_reserve(db, client.id, minute_key, incoming_event_count)
    reserved_keys[minute_key] = incoming_event_count

    if new_rate > rate_limit:
        # Undo inside the current transaction; caller owns commit/rollback.
        await _atomic_rollback(db, client.id, minute_key, incoming_event_count)
        await db.flush()
        reserved_keys.pop(minute_key, None)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded! {new_rate}/{rate_limit} events/min",
        )

    # ─── Daily Quota Check ─────────────────────────────────────────────
    if client.daily_quota:
        daily_key = f"daily:{now.strftime('%Y-%m-%d')}"
        new_daily = await _atomic_reserve(db, client.id, daily_key, incoming_event_count)
        reserved_keys[daily_key] = incoming_event_count

        if new_daily > client.daily_quota:
            # Undo inside the current transaction; caller owns commit/rollback.
            for rk, rc in reserved_keys.items():
                await _atomic_rollback(db, client.id, rk, rc)
            await db.flush()
            raise HTTPException(
                status_code=429,
                detail=f"Daily quota exceeded! Today {new_daily}/{client.daily_quota} events.",
            )

    # ─── Monthly Quota Check ───────────────────────────────────────────
    monthly_limit = getattr(client, "monthly_limit", None)
    if monthly_limit and monthly_limit > 0:
        monthly_key = f"monthly:{now.strftime('%Y-%m')}"
        new_monthly = await _atomic_reserve(db, client.id, monthly_key, incoming_event_count)
        reserved_keys[monthly_key] = incoming_event_count

        if new_monthly > monthly_limit:
            # Undo inside the current transaction; caller owns commit/rollback.
            for rk, rc in reserved_keys.items():
                await _atomic_rollback(db, client.id, rk, rc)
            await db.flush()
            raise HTTPException(
                status_code=429,
                detail=f"Monthly quota exceeded! This month {new_monthly}/{monthly_limit} events.",
            )

    # সব limit pass — commit reservations
    await db.flush()
    return reserved_keys


async def rollback_usage_reservation(
    db: AsyncSession,
    client,
    reserved_keys: dict[str, int],
) -> None:
    """
    Facebook send ফেইল হলে reserved counters rollback করো।
    এটি কল না করলেও system চলবে — শুধু count সামান্য বেশি দেখাবে।
    """
    if not reserved_keys:
        return

    usage_source = reserved_keys.get("_usage_source")
    counter_keys = {k: v for k, v in reserved_keys.items() if not k.startswith("_")}

    if not counter_keys:
        return

    if usage_source == "redis":
        # Counters were reserved in Redis — rollback via DECRBY
        r = _get_redis()
        if r is not None:
            try:
                pipe = r.pipeline()
                for window_key, event_count in counter_keys.items():
                    pipe.decrby(f"usage:{client.id}:{window_key}", event_count)
                await pipe.execute()
                logger.info(f"[{client.name}] Usage reservation rolled back in Redis: {len(counter_keys)} windows")
                return
            except Exception as exc:
                logger.warning(f"[{client.name}] Redis usage rollback failed, falling back to DB: {exc}")
        # Redis unavailable — fall through to DB rollback as best-effort

    # We do NOT commit inside the helper, we just apply modifications.
    # The caller manages the commit/rollback transaction boundary.
    for window_key, event_count in counter_keys.items():
        await _atomic_rollback(db, client.id, window_key, event_count)
    await db.flush()
    logger.info(f"[{client.name}] Usage reservation rolled back in session: {len(counter_keys)} windows")


# ─── Legacy Functions (backward compatibility) ──────────────────────────────

async def check_usage_limits_db(
    db: AsyncSession,
    client,
    incoming_event_count: int,
) -> None:
    """
    Usage limits READ-ONLY check — counter বাড়ায় না।
    Limit ছাড়ালে HTTPException(429) raise করে।

    ⚠️ Legacy: এই function-এ race condition আছে (read-then-check gap)।
    নতুন কোডে check_and_reserve_usage() ব্যবহার করুন।
    """
    now = datetime.now(timezone.utc)
    rate_limit = client.rate_limit or 5000

    # ─── Per-Minute Rate Limit Check ───────────────────────────────────
    minute_key = f"rate:{now.strftime('%Y-%m-%dT%H:%M')}"

    result = await db.execute(
        select(UsageCounter.count).where(
            UsageCounter.client_id == client.id,
            UsageCounter.window_key == minute_key,
        )
    )
    current_rate = result.scalar() or 0

    if current_rate + incoming_event_count > rate_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded! {current_rate + incoming_event_count}/{rate_limit} events/min",
        )

    # ─── Daily Quota Check ─────────────────────────────────────────────
    if client.daily_quota:
        daily_key = f"daily:{now.strftime('%Y-%m-%d')}"

        daily_result = await db.execute(
            select(UsageCounter.count).where(
                UsageCounter.client_id == client.id,
                UsageCounter.window_key == daily_key,
            )
        )
        current_daily = daily_result.scalar() or 0

        if current_daily + incoming_event_count > client.daily_quota:
            raise HTTPException(
                status_code=429,
                detail=f"Daily quota exceeded! Today {current_daily + incoming_event_count}/{client.daily_quota} events sent.",
            )

    monthly_limit = getattr(client, "monthly_limit", None)
    if monthly_limit and monthly_limit > 0:
        monthly_key = f"monthly:{now.strftime('%Y-%m')}"
        monthly_result = await db.execute(
            select(UsageCounter.count).where(
                UsageCounter.client_id == client.id,
                UsageCounter.window_key == monthly_key,
            )
        )
        current_monthly = monthly_result.scalar() or 0

        if current_monthly + incoming_event_count > monthly_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly quota exceeded! This month {current_monthly + incoming_event_count}/{monthly_limit} events sent.",
            )


async def increment_usage_counters_db(
    db: AsyncSession,
    client,
    event_count: int,
) -> None:
    """
    Usage counters atomic increment — শুধু সফল Facebook send-এর পরে কল করো।
    Atomic upsert দিয়ে counter increment করে — সব worker জুড়ে accurate।

    ⚠️ check_and_reserve_usage() ব্যবহার করলে এই function-এর দরকার নেই —
    কারণ reserve-এই counter বেড়ে গেছে। শুধু legacy call-এর জন্য রাখা হয়েছে।
    """
    now = datetime.now(timezone.utc)

    # ─── Per-Minute Rate Counter ───────────────────────────────────────
    minute_key = f"rate:{now.strftime('%Y-%m-%dT%H:%M')}"
    if engine.dialect.name == "postgresql":
        rate_stmt = (
            pg_insert(UsageCounter)
            .values(
                client_id=client.id,
                window_key=minute_key,
                count=event_count,
            )
            .on_conflict_do_update(
                constraint="uq_client_window",
                set_={"count": UsageCounter.count + event_count},
            )
        )
        await db.execute(rate_stmt)
    else:
        await _atomic_reserve(db, client.id, minute_key, event_count)

    # ─── Daily Quota Counter ───────────────────────────────────────────
    if client.daily_quota:
        daily_key = f"daily:{now.strftime('%Y-%m-%d')}"
        if engine.dialect.name == "postgresql":
            daily_stmt = (
                pg_insert(UsageCounter)
                .values(
                    client_id=client.id,
                    window_key=daily_key,
                    count=event_count,
                )
                .on_conflict_do_update(
                    constraint="uq_client_window",
                    set_={"count": UsageCounter.count + event_count},
                )
            )
            await db.execute(daily_stmt)
        else:
            await _atomic_reserve(db, client.id, daily_key, event_count)

    monthly_limit = getattr(client, "monthly_limit", None)
    if monthly_limit and monthly_limit > 0:
        monthly_key = f"monthly:{now.strftime('%Y-%m')}"
        if engine.dialect.name == "postgresql":
            monthly_stmt = (
                pg_insert(UsageCounter)
                .values(
                    client_id=client.id,
                    window_key=monthly_key,
                    count=event_count,
                )
                .on_conflict_do_update(
                    constraint="uq_client_window",
                    set_={"count": UsageCounter.count + event_count},
                )
            )
            await db.execute(monthly_stmt)
        else:
            await _atomic_reserve(db, client.id, monthly_key, event_count)

    await db.flush()
