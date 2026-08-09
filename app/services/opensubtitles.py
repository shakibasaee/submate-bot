"""OpenSubtitles search and safe subtitle-download adapter."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp

from app.bot.state import SubtitleResult
from app.core.infrastructure import infrastructure
from app.core.monitoring import monitoring
from app.core.retry import retry_async

SEARCH_URL = "https://api.opensubtitles.com/api/v1/subtitles"
DOWNLOAD_URL = "https://api.opensubtitles.com/api/v1/download"
MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
SRT_TIMECODE = re.compile(
    r"(?m)^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}"
)


class OpenSubtitlesError(Exception):
    """Safe provider error exposed without leaking request details or secrets."""


class OpenSubtitlesQuotaError(OpenSubtitlesError):
    """Raised when credentials or the provider download quota block delivery."""


class OpenSubtitlesLinkError(OpenSubtitlesError):
    """Raised when a temporary provider link is missing, invalid, or expired."""


class UnsafeSubtitleError(OpenSubtitlesError):
    """Raised when downloaded content is not a safe, valid SRT subtitle."""


class TransientOpenSubtitlesError(OpenSubtitlesError):
    """A retryable provider timeout, network error, or server response."""


@dataclass(frozen=True)
class DownloadLink:
    """A short-lived provider download URL and its suggested filename."""

    url: str
    file_name: str


def validate_srt(content: bytes) -> bytes:
    """Reject archives, oversized/binary data, and malformed subtitle text."""
    if not content:
        raise UnsafeSubtitleError("subtitle file is empty")
    if len(content) > MAX_SUBTITLE_BYTES:
        raise UnsafeSubtitleError("subtitle file is too large")
    archive_signatures = (b"PK\x03\x04", b"Rar!", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b")
    if content.startswith(archive_signatures):
        raise UnsafeSubtitleError("archives are not accepted")

    text: str | None = None
    for encoding in ("utf-8-sig", "utf-16", "cp1256", "cp1252"):
        try:
            candidate = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        control_count = sum(
            character < " " and character not in "\r\n\t" for character in candidate
        )
        if control_count <= max(2, len(candidate) // 100) and SRT_TIMECODE.search(candidate):
            text = candidate
            break
    if text is None:
        raise UnsafeSubtitleError("file is not a valid SRT subtitle")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _validate_download_url(url: str) -> None:
    """Allow only HTTPS links on OpenSubtitles-owned hosts."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "opensubtitles.com" or host.endswith(".opensubtitles.com")
    ):
        raise OpenSubtitlesLinkError("provider returned an invalid download link")


def map_subtitles(payload: dict[str, object]) -> list[SubtitleResult]:
    """Map OpenSubtitles data to minimal, user-useful selection metadata."""
    data = payload.get("data", [])
    if not isinstance(data, list):
        return []
    results: list[SubtitleResult] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
            continue
        attributes = item["attributes"]
        files = attributes.get("files", [])
        if not isinstance(files, list) or not files or not isinstance(files[0], dict):
            continue
        file_id = files[0].get("file_id")
        file_name = files[0].get("file_name", "")
        if not isinstance(file_id, int) or not isinstance(file_name, str):
            continue
        release = attributes.get("release") or file_name.rsplit(".", 1)[0]
        if not isinstance(release, str):
            continue
        extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        uploader = attributes.get("uploader")
        uploader_name = uploader.get("name") if isinstance(uploader, dict) else None
        results.append(
            SubtitleResult(
                file_id=file_id,
                release=release[:60],
                format=extension or "unknown",
                hearing_impaired=bool(attributes.get("hearing_impaired")),
                download_count=attributes.get("download_count")
                if isinstance(attributes.get("download_count"), int)
                else None,
                rating=float(attributes["ratings"])
                if isinstance(attributes.get("ratings"), (int, float))
                else None,
                uploader=uploader_name if isinstance(uploader_name, str) else None,
            )
        )
    return sorted(
        results,
        key=lambda result: (
            result.format != "srt",
            -result.rating if result.rating is not None else 0,
            -result.download_count if result.download_count is not None else 0,
        ),
    )


def _cached_subtitles(value: object) -> list[SubtitleResult] | None:
    if not isinstance(value, list):
        return None
    try:
        return [
            SubtitleResult(
                file_id=int(item["file_id"]),
                release=str(item["release"]),
                format=str(item["format"]),
                hearing_impaired=bool(item["hearing_impaired"]),
                download_count=int(item["download_count"])
                if item.get("download_count") is not None
                else None,
                rating=float(item["rating"]) if item.get("rating") is not None else None,
                uploader=str(item["uploader"]) if item.get("uploader") is not None else None,
            )
            for item in value
            if isinstance(item, dict)
        ]
    except (KeyError, TypeError, ValueError):
        return None


@dataclass
class OpenSubtitlesClient:
    """Search and safely retrieve subtitles using an OpenSubtitles API key."""

    api_key: str
    user_agent: str = "subtitle-telegram-bot v0.1"

    async def search(
        self,
        *,
        tmdb_id: int,
        language: str,
        season_number: int | None = None,
        episode_number: int | None = None,
    ) -> list[SubtitleResult]:
        """Search a movie or exact episode in the requested provider language."""
        cache_key = (
            f"opensubtitles:search:v1:{tmdb_id}:{language}:"
            f"{season_number or 0}:{episode_number or 0}"
        )
        cached = _cached_subtitles(await infrastructure.cache_get(cache_key))
        if cached is not None:
            return cached
        params: dict[str, str | int] = {"tmdb_id": tmdb_id, "languages": language}
        if season_number is not None and episode_number is not None:
            params.update({"season_number": season_number, "episode_number": episode_number})
        headers = {"Api-Key": self.api_key, "User-Agent": self.user_agent}

        async def request() -> object:
            try:
                timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.get(SEARCH_URL, params=params, headers=headers) as response,
                ):
                    if response.status in {401, 403, 406, 429}:
                        monitoring.increment("provider_quota_errors", "opensubtitles")
                        raise OpenSubtitlesQuotaError("provider unavailable or quota limited")
                    if response.status in {408, 425} or response.status >= 500:
                        raise TransientOpenSubtitlesError("provider server error")
                    if response.status != 200:
                        raise OpenSubtitlesError("provider request failed")
                    return await response.json()
            except (aiohttp.ClientError, TimeoutError) as error:
                raise TransientOpenSubtitlesError("provider request failed") from error

        try:
            payload = await retry_async(request, (TransientOpenSubtitlesError,), attempts=3)
        except TransientOpenSubtitlesError as error:
            monitoring.increment("provider_errors", "opensubtitles")
            raise OpenSubtitlesError("provider is temporarily unavailable") from error
        if not isinstance(payload, dict):
            raise OpenSubtitlesError("provider returned invalid data")
        results = map_subtitles(payload)
        await infrastructure.cache_set(
            cache_key,
            [
                {
                    "file_id": result.file_id,
                    "release": result.release,
                    "format": result.format,
                    "hearing_impaired": result.hearing_impaired,
                    "download_count": result.download_count,
                    "rating": result.rating,
                    "uploader": result.uploader,
                }
                for result in results
            ],
            infrastructure.subtitle_cache_ttl,
        )
        return results

    async def request_download_link(self, file_id: int) -> DownloadLink:
        """Exchange a validated provider file ID for a temporary SRT link."""
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
        }

        async def request() -> object:
            try:
                timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.post(
                        DOWNLOAD_URL,
                        json={"file_id": file_id, "sub_format": "srt"},
                        headers=headers,
                    ) as response,
                ):
                    if response.status in {401, 403, 406, 429}:
                        monitoring.increment("provider_quota_errors", "opensubtitles")
                        raise OpenSubtitlesQuotaError("download quota or authorization failed")
                    if response.status in {408, 425} or response.status >= 500:
                        raise TransientOpenSubtitlesError("download-link server error")
                    if response.status != 200:
                        raise OpenSubtitlesLinkError("temporary link request failed")
                    return await response.json()
            except (aiohttp.ClientError, TimeoutError) as error:
                raise TransientOpenSubtitlesError("temporary link request failed") from error

        try:
            payload = await retry_async(request, (TransientOpenSubtitlesError,), attempts=3)
        except TransientOpenSubtitlesError as error:
            monitoring.increment("provider_errors", "opensubtitles")
            raise OpenSubtitlesLinkError("temporary link request failed") from error

        if not isinstance(payload, dict):
            raise OpenSubtitlesLinkError("provider returned invalid download data")
        link = payload.get("link")
        file_name = payload.get("file_name", "subtitle.srt")
        if not isinstance(link, str) or not isinstance(file_name, str):
            raise OpenSubtitlesLinkError("provider returned no download link")
        _validate_download_url(link)
        return DownloadLink(url=link, file_name=file_name)

    async def download_srt(self, link: DownloadLink) -> bytes:
        """Download a bounded temporary link and return normalized UTF-8 SRT data."""
        _validate_download_url(link.url)

        async def request() -> bytes:
            try:
                timeout = aiohttp.ClientTimeout(total=20, connect=3, sock_read=15)
                async with (
                    aiohttp.ClientSession(timeout=timeout) as session,
                    session.get(link.url, allow_redirects=False) as response,
                ):
                    if response.status in {403, 404, 410}:
                        raise OpenSubtitlesLinkError("temporary link expired")
                    if response.status == 429:
                        monitoring.increment("provider_quota_errors", "opensubtitles")
                        raise OpenSubtitlesQuotaError("download server rate limited")
                    if response.status in {408, 425} or response.status >= 500:
                        raise TransientOpenSubtitlesError("download server error")
                    if response.status != 200:
                        raise OpenSubtitlesLinkError("subtitle download failed")
                    content_length = response.content_length
                    if content_length is not None and content_length > MAX_SUBTITLE_BYTES:
                        raise UnsafeSubtitleError("subtitle file is too large")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        total += len(chunk)
                        if total > MAX_SUBTITLE_BYTES:
                            raise UnsafeSubtitleError("subtitle file is too large")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (aiohttp.ClientError, TimeoutError) as error:
                raise TransientOpenSubtitlesError("subtitle download failed") from error

        try:
            content = await retry_async(request, (TransientOpenSubtitlesError,), attempts=3)
        except TransientOpenSubtitlesError as error:
            monitoring.increment("provider_errors", "opensubtitles")
            raise OpenSubtitlesLinkError("subtitle download failed") from error
        return validate_srt(content)
