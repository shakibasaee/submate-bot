"""Redis-backed cache and distributed rate limiting with fast memory fallback."""

import hashlib
import json

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.application.ports.rate_limits import RateLimitDecision
from app.infrastructure.cache.memory import InMemoryRateLimiter

RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


class RedisCache:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> object | None:
        try:
            value = await self._client.get(key)
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return json.loads(value) if isinstance(value, str) else None
        except (RedisError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    async def set(self, key: str, value: object, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            return
        try:
            await self._client.set(
                key,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
            )
        except (RedisError, TypeError):
            return


class RedisRateLimiter:
    def __init__(self, client: redis.Redis, fallback: InMemoryRateLimiter) -> None:
        self._client = client
        self._fallback = fallback

    async def check(
        self, scope: str, identifier: str | int, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        digest = hashlib.sha256(f"{scope}:{identifier}".encode()).hexdigest()[:32]
        key = f"rate:v1:{scope}:{digest}"
        try:
            result = await self._client.eval(
                RATE_LIMIT_SCRIPT,
                1,
                key,
                window_seconds,
                limit,
            )
            if isinstance(result, (list, tuple)) and len(result) == 2:
                count, ttl = int(result[0]), int(result[1])
                return RateLimitDecision(count <= limit, max(1, ttl) if count > limit else None)
        except (RedisError, TypeError, ValueError):
            pass
        return await self._fallback.check(scope, identifier, limit, window_seconds)
