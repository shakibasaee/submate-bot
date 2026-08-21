"""OpenSubtitles implementation of the provider-neutral subtitle port."""

import re
from urllib.parse import urlparse

import aiohttp

from app.application.ports.cache import Cache
from app.core.retry import retry_async
from app.domain.errors import (
    ProviderError,
    ProviderLinkError,
    ProviderQuotaError,
    UnsafeSubtitleError,
)
from app.domain.models import EpisodeRef, MovieRef
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
    SubtitleQuery,
)

SEARCH_URL = "https://api.opensubtitles.com/api/v1/subtitles"
DOWNLOAD_URL = "https://api.opensubtitles.com/api/v1/download"
MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
OPENSUBTITLES_ID = ProviderId("opensubtitles")
ATTRIBUTION = "Provided by OpenSubtitles.com. Subtitle copyright belongs to its respective author."
SRT_TIMECODE = re.compile(
    r"(?m)^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}"
)


class _TransientProviderError(ProviderError):
    pass


def validate_srt(content: bytes) -> bytes:
    if not content:
        raise UnsafeSubtitleError("subtitle file is empty")
    if len(content) > MAX_SUBTITLE_BYTES:
        raise UnsafeSubtitleError("subtitle file is too large")
    if content.startswith((b"PK\x03\x04", b"Rar!", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b")):
        raise UnsafeSubtitleError("archives are not accepted")
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-16", "cp1256", "cp1252"):
        try:
            candidate = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        controls = sum(char < " " and char not in "\r\n\t" for char in candidate)
        if controls <= max(2, len(candidate) // 100) and SRT_TIMECODE.search(candidate):
            text = candidate
            break
    if text is None:
        raise UnsafeSubtitleError("file is not a valid SRT subtitle")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "opensubtitles.com" or host.endswith(".opensubtitles.com")
    ):
        raise ProviderLinkError("provider returned an invalid download link")


def map_subtitles(payload: dict[str, object], query: SubtitleQuery) -> list[SubtitleCandidate]:
    data = payload.get("data", [])
    if not isinstance(data, list):
        return []
    candidates: list[SubtitleCandidate] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
            continue
        attributes = item["attributes"]
        files = attributes.get("files", [])
        if not isinstance(files, list):
            continue
        uploader = attributes.get("uploader")
        uploader_name = uploader.get("name") if isinstance(uploader, dict) else None
        for file in files:
            if not isinstance(file, dict):
                continue
            file_id = file.get("file_id")
            file_name = file.get("file_name", "")
            if not isinstance(file_id, (int, str)) or not isinstance(file_name, str):
                continue
            extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
            release = attributes.get("release") or file_name.rsplit(".", 1)[0]
            if not isinstance(release, str):
                continue
            candidates.append(
                SubtitleCandidate(
                    provider_id=OPENSUBTITLES_ID,
                    provider_file_ref=ProviderFileRef(str(file_id)),
                    language=query.language,
                    format=extension or "unknown",
                    release_name=release,
                    hearing_impaired=bool(attributes.get("hearing_impaired")),
                    forced=bool(attributes.get("foreign_parts_only")),
                    rating=float(attributes["ratings"])
                    if isinstance(attributes.get("ratings"), (int, float))
                    else None,
                    download_count=attributes.get("download_count")
                    if isinstance(attributes.get("download_count"), int)
                    else None,
                    uploader=uploader_name if isinstance(uploader_name, str) else None,
                    attribution=ATTRIBUTION,
                )
            )
    return candidates


class OpenSubtitlesProvider:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        cache: Cache,
        *,
        cache_ttl_seconds: int = 120,
        user_agent: str = "subtitle-telegram-bot v0.1",
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._headers = {"Api-Key": api_key, "User-Agent": user_agent}

    @property
    def provider_id(self) -> ProviderId:
        return OPENSUBTITLES_ID

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]:
        media = query.media
        if isinstance(media, MovieRef):
            tmdb_id = media.external_id
            season_number = episode_number = None
        elif isinstance(media, EpisodeRef):
            tmdb_id = media.series.external_id
            season_number = media.season_number
            episode_number = media.episode_number
        else:  # pragma: no cover - SubtitleQuery's type makes this defensive only.
            raise ProviderError("unsupported media query")
        key = (
            f"opensubtitles:search:v2:{tmdb_id}:{query.language}:"
            f"{season_number or 0}:{episode_number or 0}"
        )
        cached = await self._cache.get(key)
        if isinstance(cached, dict):
            return map_subtitles(cached, query)
        params: dict[str, str | int] = {
            "tmdb_id": tmdb_id,
            "languages": str(query.language),
        }
        if season_number is not None and episode_number is not None:
            params.update({"season_number": season_number, "episode_number": episode_number})

        async def request() -> dict[str, object]:
            try:
                async with self._session.get(
                    SEARCH_URL, params=params, headers=self._headers
                ) as response:
                    if response.status in {401, 403, 406, 429}:
                        raise ProviderQuotaError("provider unavailable or quota limited")
                    if response.status in {408, 425} or response.status >= 500:
                        raise _TransientProviderError("provider temporarily unavailable")
                    if response.status != 200:
                        raise ProviderError("provider request failed")
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError) as error:
                raise _TransientProviderError("provider temporarily unavailable") from error
            if not isinstance(payload, dict):
                raise ProviderError("provider returned invalid data")
            return payload

        try:
            payload = await retry_async(request, (_TransientProviderError,), attempts=3)
        except _TransientProviderError as error:
            raise ProviderError("provider temporarily unavailable") from error
        await self._cache.set(key, payload, self._cache_ttl)
        return map_subtitles(payload, query)

    async def _download_link(self, file_ref: ProviderFileRef) -> str:
        try:
            file_id = int(file_ref)
        except ValueError as error:
            raise ProviderLinkError("provider file reference is invalid") from error
        headers = {**self._headers, "Content-Type": "application/json"}
        try:
            async with self._session.post(
                DOWNLOAD_URL,
                json={"file_id": file_id, "sub_format": "srt"},
                headers=headers,
            ) as response:
                if response.status in {401, 403, 406, 429}:
                    raise ProviderQuotaError("download quota or authorization failed")
                if response.status != 200:
                    raise ProviderLinkError("temporary link request failed")
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise ProviderLinkError("temporary link request failed") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("link"), str):
            raise ProviderLinkError("provider returned no download link")
        link = payload["link"]
        _validate_download_url(link)
        return link

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle:
        if candidate.provider_id != self.provider_id:
            raise ProviderLinkError("candidate belongs to another provider")
        link = await self._download_link(candidate.provider_file_ref)
        try:
            async with self._session.get(link, allow_redirects=False) as response:
                if response.status in {403, 404, 410}:
                    raise ProviderLinkError("temporary link expired")
                if response.status == 429:
                    raise ProviderQuotaError("download server rate limited")
                if response.status != 200:
                    raise ProviderLinkError("subtitle download failed")
                if response.content_length and response.content_length > MAX_SUBTITLE_BYTES:
                    raise UnsafeSubtitleError("subtitle file is too large")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    size += len(chunk)
                    if size > MAX_SUBTITLE_BYTES:
                        raise UnsafeSubtitleError("subtitle file is too large")
                    chunks.append(chunk)
        except (aiohttp.ClientError, TimeoutError) as error:
            raise ProviderLinkError("subtitle download failed") from error
        return DownloadedSubtitle(
            content=validate_srt(b"".join(chunks)),
            filename="subtitle.srt",
            format="srt",
            attribution=candidate.attribution,
            uploader=candidate.uploader,
        )
