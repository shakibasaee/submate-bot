"""Small TMDb search client and response mapper."""

import hashlib
from dataclasses import dataclass

import aiohttp

from app.bot.state import Episode, MediaType, SearchResult, Season
from app.core.infrastructure import infrastructure
from app.core.monitoring import monitoring
from app.core.retry import retry_async

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
MAX_RESULTS = 5


class TmdbSearchError(Exception):
    """Raised when TMDb cannot provide a usable search response."""


class TransientTmdbError(TmdbSearchError):
    """A retryable TMDb timeout, network error, or server response."""


def _cached_results(value: object) -> list[SearchResult] | None:
    if not isinstance(value, list):
        return None
    try:
        return [
            SearchResult(
                int(item["tmdb_id"]),
                MediaType(item["media_type"]),
                str(item["title"]),
                str(item["year"]) if item.get("year") is not None else None,
            )
            for item in value
            if isinstance(item, dict)
        ]
    except (KeyError, TypeError, ValueError):
        return None


def _cached_seasons(value: object) -> list[Season] | None:
    if not isinstance(value, list):
        return None
    try:
        return [Season(int(item["number"]), str(item["name"])) for item in value]
    except (KeyError, TypeError, ValueError):
        return None


def _cached_episodes(value: object) -> list[Episode] | None:
    if not isinstance(value, list):
        return None
    try:
        return [Episode(int(item["number"]), str(item["name"])) for item in value]
    except (KeyError, TypeError, ValueError):
        return None


def map_seasons(payload: dict[str, object]) -> list[Season]:
    """Map TV details data, deliberately excluding specials (season 0)."""
    raw_seasons = payload.get("seasons", [])
    if not isinstance(raw_seasons, list):
        return []
    return [
        Season(number, name.strip())
        for item in raw_seasons
        if isinstance(item, dict)
        and isinstance(number := item.get("season_number"), int)
        and number > 0
        and isinstance(name := item.get("name"), str)
        and name.strip()
    ]


def map_episodes(payload: dict[str, object]) -> list[Episode]:
    """Map a selected TMDb season response to selectable episodes."""
    raw_episodes = payload.get("episodes", [])
    if not isinstance(raw_episodes, list):
        return []
    return [
        Episode(number, name.strip())
        for item in raw_episodes
        if isinstance(item, dict)
        and isinstance(number := item.get("episode_number"), int)
        and number > 0
        and isinstance(name := item.get("name"), str)
        and name.strip()
    ]


def map_search_results(payload: dict[str, object], limit: int = MAX_RESULTS) -> list[SearchResult]:
    """Map TMDb multi-search data to movies and TV series only."""
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return []

    results: list[SearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict) or item.get("media_type") not in {"movie", "tv"}:
            continue
        tmdb_id = item.get("id")
        media_type = MediaType(item["media_type"])
        title = item.get("title") if media_type is MediaType.MOVIE else item.get("name")
        date = (
            item.get("release_date")
            if media_type is MediaType.MOVIE
            else item.get("first_air_date")
        )
        if not isinstance(tmdb_id, int) or not isinstance(title, str) or not title.strip():
            continue
        year = date[:4] if isinstance(date, str) and len(date) >= 4 else None
        results.append(SearchResult(tmdb_id, media_type, title.strip(), year))
        if len(results) == limit:
            break
    return results


@dataclass
class TmdbClient:
    """Perform bounded title searches using a TMDb API key."""

    api_key: str

    async def _request_json(self, url: str, params: dict[str, str]) -> dict[str, object]:
        async def request() -> dict[str, object]:
            try:
                timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.get(url, params=params) as response,
                ):
                    if response.status == 429:
                        monitoring.increment("provider_quota_errors", "tmdb")
                        raise TransientTmdbError("TMDb rate limited the request")
                    if response.status in {408, 425} or response.status >= 500:
                        raise TransientTmdbError("TMDb server error")
                    if response.status != 200:
                        raise TmdbSearchError("TMDb returned an unsuccessful response")
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError) as error:
                raise TransientTmdbError("TMDb request failed") from error
            if not isinstance(payload, dict):
                raise TmdbSearchError("TMDb returned invalid data")
            return payload

        try:
            return await retry_async(request, (TransientTmdbError,), attempts=3)
        except TransientTmdbError as error:
            monitoring.increment("provider_errors", "tmdb")
            raise TmdbSearchError("TMDb is temporarily unavailable") from error

    async def _get(self, path: str) -> dict[str, object]:
        """Fetch one TMDb JSON object with a bounded request."""
        return await self._request_json(
            f"https://api.themoviedb.org/3{path}", {"api_key": self.api_key}
        )

    async def search(self, query: str) -> list[SearchResult]:
        """Search TMDb's multi-search endpoint and map safe result fields."""
        query_digest = hashlib.sha256(query.casefold().encode()).hexdigest()[:32]
        cache_key = f"tmdb:search:v1:{query_digest}"
        cached = _cached_results(await infrastructure.cache_get(cache_key))
        if cached is not None:
            return cached
        payload = await self._request_json(
            TMDB_SEARCH_URL,
            {"api_key": self.api_key, "query": query, "include_adult": "false"},
        )
        results = map_search_results(payload)
        await infrastructure.cache_set(
            cache_key,
            [
                {
                    "tmdb_id": result.tmdb_id,
                    "media_type": str(result.media_type),
                    "title": result.title,
                    "year": result.year,
                }
                for result in results
            ],
            infrastructure.tmdb_cache_ttl,
        )
        return results

    async def seasons(self, series_id: int) -> list[Season]:
        """Get normal seasons for a selected TV series."""
        cache_key = f"tmdb:seasons:v1:{series_id}"
        cached = _cached_seasons(await infrastructure.cache_get(cache_key))
        if cached is not None:
            return cached
        seasons = map_seasons(await self._get(f"/tv/{series_id}"))
        await infrastructure.cache_set(
            cache_key,
            [{"number": season.number, "name": season.name} for season in seasons],
            infrastructure.tmdb_cache_ttl,
        )
        return seasons

    async def episodes(self, series_id: int, season_number: int) -> list[Episode]:
        """Get episodes for a selected TV series season."""
        cache_key = f"tmdb:episodes:v1:{series_id}:{season_number}"
        cached = _cached_episodes(await infrastructure.cache_get(cache_key))
        if cached is not None:
            return cached
        episodes = map_episodes(await self._get(f"/tv/{series_id}/season/{season_number}"))
        await infrastructure.cache_set(
            cache_key,
            [{"number": episode.number, "name": episode.name} for episode in episodes],
            infrastructure.tmdb_cache_ttl,
        )
        return episodes
