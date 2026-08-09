"""PostgreSQL preferences, Redis caching, and distributed rate limiting."""

import asyncio
import hashlib
import json
import time
from typing import Any

import redis.asyncio as redis
import structlog
from psycopg import Error as PsycopgError
from psycopg_pool import AsyncConnectionPool
from redis.exceptions import RedisError

from app.core.config import Settings
from app.core.monitoring import monitoring
from app.core.retry import retry_async

logger = structlog.get_logger(__name__)

PREFERENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_preferences (
    telegram_user_id BIGINT PRIMARY KEY,
    subtitle_language VARCHAR(8) NOT NULL CHECK (subtitle_language IN ('en', 'fa')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if count <= tonumber(ARGV[2]) then
    return 1
end
return 0
"""


class Infrastructure:
    """Own optional data services and degrade safely when they are unavailable."""

    def __init__(self) -> None:
        self.redis: redis.Redis | None = None
        self.postgres: AsyncConnectionPool[Any] | None = None
        self._memory_preferences: dict[int, str] = {}
        self._memory_limits: dict[str, tuple[int, int]] = {}
        self._limit_lock = asyncio.Lock()
        self.tmdb_cache_ttl = 300
        self.subtitle_cache_ttl = 120
        self.user_search_limit = 10
        self.global_tmdb_limit = 120
        self.global_subtitle_limit = 60
        self.user_download_limit = 5
        self.global_download_limit = 20
        self._redis_configured = False
        self._postgres_configured = False
        self._settings: Settings | None = None

    async def start(self, settings: Settings) -> None:
        """Connect configured services without making either a startup requirement."""
        self._settings = settings
        self.tmdb_cache_ttl = settings.tmdb_cache_ttl_seconds
        self.subtitle_cache_ttl = settings.subtitle_cache_ttl_seconds
        self.user_search_limit = settings.user_search_limit_per_minute
        self.global_tmdb_limit = settings.global_tmdb_limit_per_minute
        self.global_subtitle_limit = settings.global_subtitle_limit_per_minute
        self.user_download_limit = settings.user_download_limit_per_10_minutes
        self.global_download_limit = settings.global_download_limit_per_minute
        await self._start_redis(settings)
        await self._start_postgres(settings)

    async def _start_redis(self, settings: Settings) -> None:
        if settings.redis_url is None:
            logger.info("redis_disabled")
            return
        self._redis_configured = True
        client = redis.Redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        try:
            await retry_async(client.ping, (RedisError, TimeoutError), attempts=3)
        except (RedisError, TimeoutError):
            await client.aclose()
            monitoring.increment("dependency_errors", "redis")
            logger.warning("redis_unavailable", fallback="direct_api_and_memory_limits")
            return
        self.redis = client
        logger.info("redis_connected")

    async def _start_postgres(self, settings: Settings) -> None:
        if settings.database_url is None:
            logger.info("postgres_disabled")
            return
        self._postgres_configured = True
        pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
            settings.database_url.get_secret_value(),
            min_size=1,
            max_size=5,
            timeout=5,
            open=False,
        )
        try:
            await pool.open(wait=True, timeout=5)
            async with pool.connection() as connection:
                await connection.execute(PREFERENCE_SCHEMA)
        except (PsycopgError, TimeoutError):
            await pool.close()
            monitoring.increment("dependency_errors", "postgres")
            logger.warning("postgres_unavailable", fallback="process_memory_preferences")
            return
        self.postgres = pool
        logger.info("postgres_connected")

    async def close(self) -> None:
        """Close initialized service clients during bot shutdown."""
        if self.redis is not None:
            await self.redis.aclose()
            self.redis = None
        if self.postgres is not None:
            await self.postgres.close()
            self.postgres = None
        self._settings = None

    async def save_language(self, user_id: int, language: str) -> None:
        """Persist only the Telegram ID and selected subtitle language."""
        self._memory_preferences[user_id] = language
        postgres = self.postgres
        if postgres is None:
            return

        async def save() -> None:
            async with postgres.connection(timeout=3) as connection:
                await connection.execute(
                    """
                    INSERT INTO user_preferences (telegram_user_id, subtitle_language)
                    VALUES (%s, %s)
                    ON CONFLICT (telegram_user_id) DO UPDATE
                    SET subtitle_language = EXCLUDED.subtitle_language, updated_at = NOW()
                    """,
                    (user_id, language),
                )

        try:
            await retry_async(save, (PsycopgError, TimeoutError), attempts=2)
        except (PsycopgError, TimeoutError):
            monitoring.increment("dependency_errors", "postgres")
            logger.warning("preference_write_failed")

    async def load_language(self, user_id: int) -> str | None:
        """Load a preference from PostgreSQL, falling back to process memory."""
        postgres = self.postgres
        if postgres is not None:

            async def load() -> tuple[object, ...] | None:
                async with postgres.connection(timeout=3) as connection:
                    cursor = await connection.execute(
                        "SELECT subtitle_language FROM user_preferences "
                        "WHERE telegram_user_id = %s",
                        (user_id,),
                    )
                    return await cursor.fetchone()

            try:
                row = await retry_async(load, (PsycopgError, TimeoutError), attempts=2)
                if row and row[0] in {"en", "fa"}:
                    self._memory_preferences[user_id] = str(row[0])
                    return str(row[0])
            except (PsycopgError, TimeoutError):
                monitoring.increment("dependency_errors", "postgres")
                logger.warning("preference_read_failed")
        return self._memory_preferences.get(user_id)

    async def cache_get(self, key: str) -> Any | None:
        """Read JSON from Redis; a failure behaves exactly like a cache miss."""
        redis_client = self.redis
        if redis_client is None:
            return None

        async def get() -> str | None:
            value = await redis_client.get(key)
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return value

        try:
            value = await retry_async(get, (RedisError, TimeoutError), attempts=2)
            return json.loads(value) if value is not None else None
        except (RedisError, TimeoutError, json.JSONDecodeError):
            monitoring.increment("dependency_errors", "redis")
            logger.warning("cache_read_failed")
            return None

    async def cache_set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Write expiring JSON to Redis and ignore cache-only failures."""
        redis_client = self.redis
        if redis_client is None or ttl_seconds <= 0:
            return

        async def set_value() -> None:
            await redis_client.set(
                key,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
            )

        try:
            await retry_async(set_value, (RedisError, TimeoutError), attempts=2)
        except (RedisError, TimeoutError, TypeError):
            monitoring.increment("dependency_errors", "redis")
            logger.warning("cache_write_failed")

    async def allow(self, scope: str, identifier: str | int, limit: int, window: int) -> bool:
        """Apply a Redis fixed-window limit with an in-process safety fallback."""
        if limit <= 0:
            return False
        digest = hashlib.sha256(f"{scope}:{identifier}".encode()).hexdigest()[:32]
        key = f"rate:{scope}:{digest}"
        if self.redis is not None:
            try:
                allowed = await self.redis.eval(RATE_LIMIT_SCRIPT, 1, key, window, limit)
                decision = bool(allowed)
                if not decision:
                    monitoring.increment("rate_limit_rejections", scope)
                return decision
            except (RedisError, TimeoutError):
                monitoring.increment("dependency_errors", "redis")
                logger.warning("rate_limit_redis_failed", fallback="process_memory")
        decision = await self._allow_in_memory(key, limit, window)
        if not decision:
            monitoring.increment("rate_limit_rejections", scope)
        return decision

    async def health(self) -> dict[str, str | bool]:
        """Check configured dependencies without exposing endpoints or credentials."""
        result: dict[str, str | bool] = {}
        ready = True
        if self._redis_configured and self.redis is None and self._settings is not None:
            await self._start_redis(self._settings)
        if self._postgres_configured and self.postgres is None and self._settings is not None:
            await self._start_postgres(self._settings)
        if not self._redis_configured:
            result["redis"] = "disabled"
        elif self.redis is None:
            result["redis"] = "unavailable"
            ready = False
        else:
            try:
                async with asyncio.timeout(2):
                    await retry_async(self.redis.ping, (RedisError, TimeoutError), attempts=2)
                result["redis"] = "ok"
            except (RedisError, TimeoutError):
                result["redis"] = "unavailable"
                ready = False

        if not self._postgres_configured:
            result["postgres"] = "disabled"
        elif self.postgres is None:
            result["postgres"] = "unavailable"
            ready = False
        else:
            try:
                async with asyncio.timeout(2), self.postgres.connection(timeout=2) as connection:
                    await connection.execute("SELECT 1")
                result["postgres"] = "ok"
            except (PsycopgError, TimeoutError):
                result["postgres"] = "unavailable"
                ready = False
        result["ready"] = ready
        return result

    async def _allow_in_memory(self, key: str, limit: int, window: int) -> bool:
        bucket = int(time.monotonic() // window)
        async with self._limit_lock:
            saved_bucket, count = self._memory_limits.get(key, (bucket, 0))
            if saved_bucket != bucket:
                count = 0
            count += 1
            self._memory_limits[key] = (bucket, count)
            if len(self._memory_limits) > 10_000:
                self._memory_limits = {
                    item_key: value
                    for item_key, value in self._memory_limits.items()
                    if value[0] == bucket
                }
            return count <= limit


infrastructure = Infrastructure()
