"""Composition root: construct and own every external application dependency."""

from dataclasses import dataclass
from typing import Any

import aiohttp
import redis.asyncio as redis
import structlog
from psycopg import Error as PsycopgError
from psycopg_pool import AsyncConnectionPool
from redis.exceptions import RedisError

from app.application.container import ApplicationServices
from app.application.dto import ApplicationLimits
from app.application.ports.metadata import MetadataGateway
from app.application.use_cases import (
    CancelWorkflow,
    ChooseLanguage,
    DeliverSubtitle,
    FindSubtitles,
    NavigateSeries,
    SearchTitles,
    SelectTitle,
    StartSearch,
)
from app.core.config import Settings
from app.domain.errors import ConfigurationError, MetadataError
from app.domain.models import EpisodeRef, MediaSearchResult, SeasonSummary, SeriesRef
from app.domain.subtitles import DownloadedSubtitle, ProviderId, SubtitleCandidate, SubtitleQuery
from app.infrastructure.cache.memory import InMemoryCache, InMemoryRateLimiter
from app.infrastructure.cache.redis import RedisCache, RedisRateLimiter
from app.infrastructure.metadata.tmdb import TmdbMetadataGateway
from app.infrastructure.persistence.memory import (
    InMemoryConversationRepository,
    InMemoryPreferenceRepository,
    InMemoryUserLockManager,
)
from app.infrastructure.persistence.postgres import PostgresPreferenceRepository
from app.infrastructure.providers.opensubtitles import OpenSubtitlesProvider

logger = structlog.get_logger(__name__)


class UnconfiguredMetadataGateway:
    async def search(self, query: str) -> list[MediaSearchResult]:
        raise MetadataError("Title search is not configured yet. Please try again later.")

    async def seasons(self, series: SeriesRef) -> list[SeasonSummary]:
        raise MetadataError("TV navigation is not configured yet. Please try again later.")

    async def episodes(self, series: SeriesRef, season_number: int) -> list[EpisodeRef]:
        raise MetadataError("TV navigation is not configured yet. Please try again later.")


class UnconfiguredSubtitleProvider:
    @property
    def provider_id(self) -> ProviderId:
        return ProviderId("unconfigured")

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]:
        raise ConfigurationError("Subtitle search is not configured yet. Please try again later.")

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle:
        raise ConfigurationError("Subtitle delivery is not configured yet. Please try again later.")


@dataclass(slots=True)
class ApplicationRuntime:
    services: ApplicationServices
    http_session: aiohttp.ClientSession
    redis_client: redis.Redis | None = None
    postgres_pool: AsyncConnectionPool[Any] | None = None

    async def health(self) -> dict[str, str | bool]:
        result: dict[str, str | bool] = {}
        ready = True
        if self.redis_client is None:
            result["redis"] = "disabled"
        else:
            try:
                await self.redis_client.ping()
                result["redis"] = "ok"
            except (RedisError, TimeoutError):
                result["redis"] = "unavailable"
                ready = False
        if self.postgres_pool is None:
            result["postgres"] = "disabled"
        else:
            try:
                async with self.postgres_pool.connection(timeout=2) as connection:
                    await connection.execute("SELECT 1")
                result["postgres"] = "ok"
            except (PsycopgError, TimeoutError):
                result["postgres"] = "unavailable"
                ready = False
        result["ready"] = ready
        return result

    async def close(self) -> None:
        if self.postgres_pool is not None:
            await self.postgres_pool.close()
            self.postgres_pool = None
        if self.redis_client is not None:
            await self.redis_client.aclose()
            self.redis_client = None
        if not self.http_session.closed:
            await self.http_session.close()


async def build_runtime(settings: Settings) -> ApplicationRuntime:
    """Build the object graph once and close partial resources on startup failure."""
    timeout = aiohttp.ClientTimeout(total=20, connect=3, sock_connect=3, sock_read=15)
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=20, ttl_dns_cache=300)
    session = aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers={"User-Agent": "subtitle-telegram-bot/0.1"},
    )
    redis_client: redis.Redis | None = None
    postgres_pool: AsyncConnectionPool[Any] | None = None
    try:
        memory_cache = InMemoryCache()
        memory_limiter = InMemoryRateLimiter()
        cache = memory_cache
        rate_limiter = memory_limiter
        if settings.redis_url is not None:
            candidate = redis.Redis.from_url(
                settings.redis_url.get_secret_value(),
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            try:
                await candidate.ping()
                redis_client = candidate
                cache = RedisCache(candidate)
                rate_limiter = RedisRateLimiter(candidate, memory_limiter)
            except (RedisError, TimeoutError):
                await candidate.aclose()
                logger.warning("redis_unavailable", fallback="memory")

        memory_preferences = InMemoryPreferenceRepository()
        preferences = memory_preferences
        if settings.database_url is not None:
            pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
                settings.database_url.get_secret_value(),
                min_size=1,
                max_size=5,
                timeout=5,
                open=False,
            )
            try:
                await pool.open(wait=True, timeout=5)
                postgres_preferences = PostgresPreferenceRepository(pool, memory_preferences)
                await postgres_preferences.ensure_schema()
                postgres_pool = pool
                preferences = postgres_preferences
            except (PsycopgError, TimeoutError):
                await pool.close()
                logger.warning("postgres_unavailable", fallback="memory")

        conversations = InMemoryConversationRepository()
        locks = InMemoryUserLockManager()
        tmdb_key = settings.tmdb_api_key
        metadata: MetadataGateway
        if tmdb_key is None or tmdb_key.get_secret_value().startswith("replace-"):
            metadata = UnconfiguredMetadataGateway()
        else:
            metadata = TmdbMetadataGateway(
                session,
                tmdb_key.get_secret_value(),
                cache,
                cache_ttl_seconds=settings.tmdb_cache_ttl_seconds,
            )

        providers: tuple[OpenSubtitlesProvider | UnconfiguredSubtitleProvider, ...]
        opensubtitles_key = settings.opensubtitles_api_key
        if opensubtitles_key is not None and not opensubtitles_key.get_secret_value().startswith(
            "replace-"
        ):
            providers = (
                OpenSubtitlesProvider(
                    session,
                    opensubtitles_key.get_secret_value(),
                    cache,
                    cache_ttl_seconds=settings.subtitle_cache_ttl_seconds,
                ),
            )
        else:
            providers = (UnconfiguredSubtitleProvider(),)

        limits = ApplicationLimits(
            user_search=settings.user_search_limit_per_minute,
            user_download=settings.user_download_limit_per_10_minutes,
        )
        find_subtitles = FindSubtitles(
            conversations,
            providers,
            rate_limiter,
            locks,
            page_size=limits.subtitle_page_size,
            user_limit=limits.user_search,
            global_limit=settings.global_subtitle_limit_per_minute,
        )
        services = ApplicationServices(
            start_search=StartSearch(conversations, preferences, locks),
            choose_language=ChooseLanguage(conversations, preferences, locks),
            search_titles=SearchTitles(
                conversations,
                metadata,
                rate_limiter,
                locks,
                user_limit=limits.user_search,
                global_limit=settings.global_tmdb_limit_per_minute,
            ),
            select_title=SelectTitle(conversations, metadata, find_subtitles, locks),
            navigate_series=NavigateSeries(conversations, metadata, find_subtitles, locks),
            find_subtitles=find_subtitles,
            deliver_subtitle=DeliverSubtitle(
                conversations,
                {provider.provider_id: provider for provider in providers},
                rate_limiter,
                locks,
                user_limit=limits.user_download,
                global_limit=settings.global_download_limit_per_minute,
            ),
            cancel_workflow=CancelWorkflow(conversations, locks),
        )
        return ApplicationRuntime(services, session, redis_client, postgres_pool)
    except BaseException:
        if postgres_pool is not None:
            await postgres_pool.close()
        if redis_client is not None:
            await redis_client.aclose()
        await session.close()
        raise
