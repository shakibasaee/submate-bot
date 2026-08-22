"""TMDb metadata gateway using the process-wide HTTP session."""

import hashlib

import aiohttp

from app.application.ports.cache import Cache
from app.core.retry import retry_async
from app.domain.errors import MetadataError
from app.domain.models import EpisodeRef, MediaSearchResult, MediaType, SeasonSummary, SeriesRef

TMDB_API_URL = "https://api.themoviedb.org/3"
MAX_RESULTS = 5


class _TransientMetadataError(MetadataError):
    pass


def map_search_results(
    payload: dict[str, object], limit: int = MAX_RESULTS
) -> list[MediaSearchResult]:
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return []
    results: list[MediaSearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict) or item.get("media_type") not in {"movie", "tv"}:
            continue
        media_type = MediaType(str(item["media_type"]))
        external_id = item.get("id")
        title = item.get("title") if media_type is MediaType.MOVIE else item.get("name")
        date = (
            item.get("release_date")
            if media_type is MediaType.MOVIE
            else item.get("first_air_date")
        )
        if not isinstance(external_id, int) or not isinstance(title, str) or not title.strip():
            continue
        year = date[:4] if isinstance(date, str) and len(date) >= 4 else None
        results.append(MediaSearchResult(str(external_id), media_type, title.strip(), year))
        if len(results) >= limit:
            break
    return results


def map_seasons(payload: dict[str, object]) -> list[SeasonSummary]:
    raw = payload.get("seasons", [])
    if not isinstance(raw, list):
        return []
    return [
        SeasonSummary(number, name.strip())
        for item in raw
        if isinstance(item, dict)
        and isinstance(number := item.get("season_number"), int)
        and number > 0
        and isinstance(name := item.get("name"), str)
        and name.strip()
    ]


def map_episodes(payload: dict[str, object], series: SeriesRef) -> list[EpisodeRef]:
    raw = payload.get("episodes", [])
    if not isinstance(raw, list):
        return []
    season_number = payload.get("season_number")
    if not isinstance(season_number, int) or season_number < 1:
        return []
    return [
        EpisodeRef(str(external_id), series, season_number, number, name.strip())
        for item in raw
        if isinstance(item, dict)
        and isinstance(external_id := item.get("id"), int)
        and not isinstance(external_id, bool)
        and isinstance(number := item.get("episode_number"), int)
        and number > 0
        and isinstance(name := item.get("name"), str)
        and name.strip()
    ]


class TmdbMetadataGateway:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        cache: Cache,
        *,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds

    async def _request(self, path: str, params: dict[str, str]) -> dict[str, object]:
        async def request() -> dict[str, object]:
            try:
                async with self._session.get(
                    f"{TMDB_API_URL}{path}",
                    params={"api_key": self._api_key, **params},
                ) as response:
                    if response.status in {408, 425, 429} or response.status >= 500:
                        raise _TransientMetadataError("TMDb is temporarily unavailable")
                    if response.status != 200:
                        raise MetadataError("TMDb request failed")
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError) as error:
                raise _TransientMetadataError("TMDb is temporarily unavailable") from error
            if not isinstance(payload, dict):
                raise MetadataError("TMDb returned invalid data")
            return payload

        try:
            return await retry_async(request, (_TransientMetadataError,), attempts=3)
        except _TransientMetadataError as error:
            raise MetadataError("TMDb is temporarily unavailable") from error

    async def search(self, query: str) -> list[MediaSearchResult]:
        digest = hashlib.sha256(query.casefold().encode()).hexdigest()[:32]
        key = f"tmdb:search:v2:{digest}"
        cached = await self._cache.get(key)
        if isinstance(cached, list):
            try:
                return [
                    MediaSearchResult(
                        str(item["external_id"]),
                        MediaType(str(item["media_type"])),
                        str(item["title"]),
                        str(item["year"]) if item.get("year") is not None else None,
                    )
                    for item in cached
                    if isinstance(item, dict)
                ]
            except (KeyError, TypeError, ValueError):
                pass
        results = map_search_results(
            await self._request("/search/multi", {"query": query, "include_adult": "false"})
        )
        await self._cache.set(
            key,
            [
                {
                    "external_id": item.external_id,
                    "media_type": str(item.media_type),
                    "title": item.title,
                    "year": item.year,
                }
                for item in results
            ],
            self._cache_ttl,
        )
        return results

    async def seasons(self, series: SeriesRef) -> list[SeasonSummary]:
        key = f"tmdb:seasons:v2:{series.external_id}"
        cached = await self._cache.get(key)
        if isinstance(cached, list):
            try:
                return [SeasonSummary(int(x["number"]), str(x["name"])) for x in cached]
            except (KeyError, TypeError, ValueError):
                pass
        results = map_seasons(await self._request(f"/tv/{series.external_id}", {}))
        await self._cache.set(
            key,
            [{"number": item.number, "name": item.name} for item in results],
            self._cache_ttl,
        )
        return results

    async def episodes(self, series: SeriesRef, season_number: int) -> list[EpisodeRef]:
        key = f"tmdb:episodes:v3:{series.external_id}:{season_number}"
        cached = await self._cache.get(key)
        if isinstance(cached, list):
            try:
                return [
                    EpisodeRef(
                        str(x["external_id"]),
                        series,
                        season_number,
                        int(x["number"]),
                        str(x["name"]),
                    )
                    for x in cached
                ]
            except (KeyError, TypeError, ValueError):
                pass
        payload = await self._request(f"/tv/{series.external_id}/season/{season_number}", {})
        payload.setdefault("season_number", season_number)
        results = map_episodes(payload, series)
        await self._cache.set(
            key,
            [
                {
                    "external_id": item.external_id,
                    "number": item.episode_number,
                    "name": item.name,
                }
                for item in results
            ],
            self._cache_ttl,
        )
        return results
