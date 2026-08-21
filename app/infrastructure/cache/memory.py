"""Safe single-process cache and fixed-window limiter fallbacks."""

import asyncio
import time
from collections.abc import Callable

from app.application.ports.rate_limits import RateLimitDecision


class InMemoryCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[object, float]] = {}

    async def get(self, key: str) -> object | None:
        saved = self._values.get(key)
        if saved is None:
            return None
        value, expires_at = saved
        if expires_at <= self._clock():
            self._values.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: object, ttl_seconds: int) -> None:
        if ttl_seconds > 0:
            self._values[key] = (value, self._clock() + ttl_seconds)


class InMemoryRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._buckets: dict[tuple[str, str], tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def check(
        self, scope: str, identifier: str | int, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        if limit < 1:
            return RateLimitDecision(False, window_seconds)
        bucket = int(self._clock() // window_seconds)
        key = (scope, str(identifier))
        async with self._lock:
            saved_bucket, count = self._buckets.get(key, (bucket, 0))
            if saved_bucket != bucket:
                count = 0
            count += 1
            self._buckets[key] = (bucket, count)
        if count <= limit:
            return RateLimitDecision(True)
        retry_after = window_seconds - int(self._clock() % window_seconds)
        return RateLimitDecision(False, max(1, retry_after))
