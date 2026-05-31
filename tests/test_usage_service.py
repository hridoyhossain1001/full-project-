import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-api-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("ENCRYPTION_KEY", "ZFhnf1szwemka8kBbH9jPTC7oKBRTEv0EqWt1J8AD0M=")

from app.services import usage_service


class _Pipeline:
    def __init__(self):
        self.commands = []

    def incrby(self, key, value):
        self.commands.append(("incrby", key, value))

    def expire(self, key, value, nx=False):
        self.commands.append(("expire", key, value, nx))

    def decrby(self, key, value):
        self.commands.append(("decrby", key, value))

    async def execute(self):
        if any(command[0] == "incrby" for command in self.commands):
            return [1, True, 1, True, 1, True]
        return [1 for _ in self.commands]


class _Redis:
    def __init__(self):
        self.pipelines = []

    def pipeline(self):
        pipe = _Pipeline()
        self.pipelines.append(pipe)
        return pipe


class _Db:
    async def flush(self):
        return None


@pytest.mark.anyio
async def test_dual_usage_reservation_rolls_back_redis_and_db(monkeypatch):
    redis = _Redis()
    db_rollbacks = []

    async def reserve(_db, _client_id, _key, count):
        return count

    async def rollback(_db, _client_id, key, count):
        db_rollbacks.append((key, count))

    monkeypatch.setattr(usage_service, "USAGE_DB_SYNC_IN_REQUEST", True)
    monkeypatch.setattr(usage_service, "_get_redis", lambda: redis)
    monkeypatch.setattr(usage_service, "_atomic_reserve", reserve)
    monkeypatch.setattr(usage_service, "_atomic_rollback", rollback)

    client = SimpleNamespace(id=7, name="Test", rate_limit=10, daily_quota=20, monthly_limit=30)
    reserved = await usage_service.check_and_reserve_usage(_Db(), client, 1)

    assert reserved["_usage_source"] == "redis"
    assert reserved["_usage_db_synced"] == 1

    await usage_service.rollback_usage_reservation(_Db(), client, reserved)

    assert len(db_rollbacks) == 3
    assert all(not key.startswith("_") for key, _count in db_rollbacks)
    redis_rollbacks = [command for command in redis.pipelines[-1].commands if command[0] == "decrby"]
    assert len(redis_rollbacks) == 3


@pytest.mark.anyio
async def test_dual_usage_reservation_cleans_redis_when_db_quota_rejects(monkeypatch):
    redis = _Redis()
    reservations = iter([1, 99])

    async def reserve(_db, _client_id, _key, _count):
        return next(reservations)

    async def rollback(_db, _client_id, _key, _count):
        return None

    monkeypatch.setattr(usage_service, "USAGE_DB_SYNC_IN_REQUEST", True)
    monkeypatch.setattr(usage_service, "_get_redis", lambda: redis)
    monkeypatch.setattr(usage_service, "_atomic_reserve", reserve)
    monkeypatch.setattr(usage_service, "_atomic_rollback", rollback)

    client = SimpleNamespace(id=7, name="Test", rate_limit=10, daily_quota=20, monthly_limit=30)
    with pytest.raises(Exception) as exc_info:
        await usage_service.check_and_reserve_usage(_Db(), client, 1)

    assert getattr(exc_info.value, "status_code", None) == 429
    redis_rollbacks = [command for command in redis.pipelines[-1].commands if command[0] == "decrby"]
    assert len(redis_rollbacks) == 3
