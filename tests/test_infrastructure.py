"""Tests for cache fallback, preference fallback, and fixed-window limits."""

import asyncio

from redis.exceptions import RedisError

from app.core import infrastructure as infrastructure_module
from app.core.infrastructure import Infrastructure


class WorkingRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiry: int | None = None

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expiry = ex


class FailingRedis:
    async def get(self, key: str) -> None:
        raise RedisError("redis unavailable")

    async def set(self, key: str, value: str, *, ex: int) -> None:
        raise RedisError("redis unavailable")

    async def eval(self, script: str, key_count: int, *arguments: object) -> None:
        raise RedisError("redis unavailable")


def test_cache_values_have_expiry_and_round_trip() -> None:
    service = Infrastructure()
    redis = WorkingRedis()
    service.redis = redis  # type: ignore[assignment]

    asyncio.run(service.cache_set("title", {"id": 1}, 120))

    assert redis.expiry == 120
    assert asyncio.run(service.cache_get("title")) == {"id": 1}


def test_redis_failure_falls_back_to_cache_miss_and_memory_limit() -> None:
    service = Infrastructure()
    service.redis = FailingRedis()  # type: ignore[assignment]

    assert asyncio.run(service.cache_get("missing")) is None
    assert asyncio.run(service.allow("search", 7, 1, 60)) is True
    assert asyncio.run(service.allow("search", 7, 1, 60)) is False


def test_memory_rate_limit_resets_after_expiry(monkeypatch: object) -> None:
    service = Infrastructure()
    clock = {"now": 0.0}
    monkeypatch.setattr(infrastructure_module.time, "monotonic", lambda: clock["now"])  # type: ignore[attr-defined]

    assert asyncio.run(service.allow("download", 9, 2, 60)) is True
    assert asyncio.run(service.allow("download", 9, 2, 60)) is True
    assert asyncio.run(service.allow("download", 9, 2, 60)) is False
    clock["now"] = 61.0
    assert asyncio.run(service.allow("download", 9, 2, 60)) is True


def test_language_preference_uses_memory_when_postgres_is_unavailable() -> None:
    service = Infrastructure()

    asyncio.run(service.save_language(123, "fa"))

    assert asyncio.run(service.load_language(123)) == "fa"
