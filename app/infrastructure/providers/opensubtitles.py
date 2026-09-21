"""OpenSubtitles implementation of the provider-neutral subtitle port."""

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

import aiohttp

from app.application.ports.cache import Cache
from app.core.retry import retry_async
from app.domain.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderLinkError,
    ProviderNotFoundError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
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

DEFAULT_API_HOST = "api.opensubtitles.com"
APPROVED_API_HOSTS = frozenset({DEFAULT_API_HOST, "vip-api.opensubtitles.com"})
MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
OPENSUBTITLES_ID = ProviderId("opensubtitles")
ATTRIBUTION = "Provided by OpenSubtitles.com. Subtitle copyright belongs to its respective author."
SRT_TIMECODE = re.compile(
    r"(?m)^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}"
)
RETRYABLE_HTTP_STATUSES = frozenset({500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class _Authentication:
    token: str
    api_host: str


class _TokenRejected(Exception):
    """Internal signal used only by the bounded authentication recovery path."""


class _TransientProviderFailure(Exception):
    def __init__(self, normalized: ProviderError) -> None:
        super().__init__(str(normalized))
        self.normalized = normalized


def _api_url(host: str, endpoint: str) -> str:
    return f"https://{host}/api/v1/{endpoint}"


def _validated_api_host(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ProviderResponseError("OpenSubtitles returned an invalid API host")
    host = value.casefold()
    if host not in APPROVED_API_HOSTS:
        raise ProviderResponseError("OpenSubtitles returned an unapproved API host")
    return host


def _retry_after(headers: Mapping[str, str]) -> int | None:
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return max(0, seconds)


def _tmdb_id(value: str, *, label: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise ProviderResponseError(f"{label} TMDb ID is invalid") from None
    if result < 1:
        raise ProviderResponseError(f"{label} TMDb ID is invalid")
    return result


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
    try:
        port = parsed.port
    except ValueError:
        raise ProviderLinkError("provider returned an invalid download link") from None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or not (host == "opensubtitles.com" or host.endswith(".opensubtitles.com"))
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
            if (
                isinstance(file_id, bool)
                or not isinstance(file_id, (int, str))
                or not str(file_id)
                or not isinstance(file_name, str)
            ):
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
        username: str | None = None,
        password: str | None = None,
        cache_ttl_seconds: int = 120,
        user_agent: str = "subtitle-telegram-bot v0.1",
        retry_base_delay: float = 0.25,
        retry_jitter: float = 0.2,
    ) -> None:
        self._session = session
        self._api_key = api_key.strip()
        self._username = username.strip() if username is not None else None
        self._password = password
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._user_agent = user_agent
        self._retry_base_delay = retry_base_delay
        self._retry_jitter = retry_jitter
        self._authentication: _Authentication | None = None
        self._authentication_lock = asyncio.Lock()

    @property
    def provider_id(self) -> ProviderId:
        return OPENSUBTITLES_ID

    def _headers(self, *, token: str | None = None, json_request: bool = False) -> dict[str, str]:
        if not self._configured_value(self._api_key):
            raise ProviderConfigurationError("OpenSubtitles API key is not configured")
        headers = {"Api-Key": self._api_key, "User-Agent": self._user_agent}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if json_request:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _configured_value(value: str | None) -> bool:
        return bool(value and value.strip() and not value.strip().startswith("replace-"))

    async def _retry_transient[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        try:
            return await retry_async(
                operation,
                (_TransientProviderFailure,),
                attempts=3,
                base_delay=self._retry_base_delay,
                jitter=self._retry_jitter,
            )
        except _TransientProviderFailure as error:
            raise error.normalized from None

    @staticmethod
    def _raise_transient_status(status: int, headers: Mapping[str, str]) -> None:
        if status == 429:
            raise _TransientProviderFailure(
                ProviderRateLimitError(
                    "OpenSubtitles rate limit reached",
                    retry_after=_retry_after(headers),
                )
            )
        if status == 408:
            raise _TransientProviderFailure(ProviderTimeoutError("OpenSubtitles timed out"))
        if status == 425 or status in RETRYABLE_HTTP_STATUSES:
            raise _TransientProviderFailure(
                ProviderUnavailableError("OpenSubtitles is temporarily unavailable")
            )

    @staticmethod
    async def _json_payload(response: aiohttp.ClientResponse) -> dict[str, object]:
        try:
            payload: object = await response.json()
        except (aiohttp.ContentTypeError, ValueError):
            raise ProviderResponseError("OpenSubtitles returned malformed JSON") from None
        if not isinstance(payload, dict):
            raise ProviderResponseError("OpenSubtitles returned invalid data")
        return payload

    async def _login_request(self) -> _Authentication:
        if not self._configured_value(self._username) or not self._configured_value(self._password):
            raise ProviderConfigurationError(
                "OpenSubtitles username and password are required for subtitle downloads"
            )

        async def request() -> _Authentication:
            try:
                async with self._session.post(
                    _api_url(DEFAULT_API_HOST, "login"),
                    json={"username": self._username, "password": self._password},
                    headers=self._headers(json_request=True),
                ) as response:
                    self._raise_transient_status(response.status, response.headers)
                    if response.status in {401, 403}:
                        raise ProviderAuthenticationError(
                            "OpenSubtitles rejected the configured credentials or API key"
                        )
                    if response.status == 404:
                        raise ProviderNotFoundError("OpenSubtitles login endpoint was not found")
                    if response.status != 200:
                        raise ProviderResponseError("OpenSubtitles rejected the login request")
                    payload = await self._json_payload(response)
            except TimeoutError as error:
                raise _TransientProviderFailure(
                    ProviderTimeoutError("OpenSubtitles login timed out")
                ) from error
            except (aiohttp.ClientConnectionError, ConnectionResetError) as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles connection failed")
                ) from error
            except aiohttp.ClientError as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles login failed")
                ) from error

            token = payload.get("token")
            if not isinstance(token, str) or not token:
                raise ProviderResponseError("OpenSubtitles login response did not contain a token")
            return _Authentication(token, _validated_api_host(payload.get("base_url")))

        return await self._retry_transient(request)

    async def _authentication_for_request(self) -> _Authentication:
        authentication = self._authentication
        if authentication is not None:
            return authentication
        async with self._authentication_lock:
            if self._authentication is None:
                self._authentication = await self._login_request()
            return self._authentication

    async def _refresh_authentication(self, rejected_token: str) -> _Authentication:
        async with self._authentication_lock:
            current = self._authentication
            if current is not None and current.token != rejected_token:
                return current
            self._authentication = None
            self._authentication = await self._login_request()
            return self._authentication

    async def _invalidate_authentication(self, rejected_token: str) -> None:
        async with self._authentication_lock:
            if self._authentication is not None and self._authentication.token == rejected_token:
                self._authentication = None

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]:
        media = query.media
        parent_tmdb_id: int | None = None
        if isinstance(media, MovieRef):
            tmdb_id = _tmdb_id(media.external_id, label="movie")
            season_number = episode_number = None
        elif isinstance(media, EpisodeRef):
            tmdb_id = _tmdb_id(media.external_id, label="episode")
            parent_tmdb_id = _tmdb_id(media.series.external_id, label="series")
            season_number = media.season_number
            episode_number = media.episode_number
        else:  # pragma: no cover - SubtitleQuery's type makes this defensive only.
            raise ProviderResponseError("unsupported media query")
        key = (
            f"opensubtitles:search:v3:{tmdb_id}:{parent_tmdb_id or 0}:"
            f"{query.language}:{season_number or 0}:{episode_number or 0}"
        )
        cached = await self._cache.get(key)
        if isinstance(cached, dict) and isinstance(cached.get("data"), list):
            return map_subtitles(cached, query)
        params: dict[str, str | int] = {
            "tmdb_id": tmdb_id,
            "languages": str(query.language),
        }
        if parent_tmdb_id is not None and season_number is not None and episode_number is not None:
            params.update(
                {
                    "parent_tmdb_id": parent_tmdb_id,
                    "season_number": season_number,
                    "episode_number": episode_number,
                }
            )

        async def request() -> dict[str, object]:
            try:
                async with self._session.get(
                    _api_url(DEFAULT_API_HOST, "subtitles"),
                    params=params,
                    headers=self._headers(),
                ) as response:
                    self._raise_transient_status(response.status, response.headers)
                    if response.status in {401, 403}:
                        raise ProviderAuthenticationError(
                            "OpenSubtitles rejected the configured API key"
                        )
                    if response.status == 404:
                        raise ProviderNotFoundError("OpenSubtitles found no matching resource")
                    if response.status == 406:
                        raise ProviderQuotaError("OpenSubtitles request quota was rejected")
                    if response.status != 200:
                        raise ProviderResponseError("OpenSubtitles rejected the search request")
                    payload = await self._json_payload(response)
            except TimeoutError as error:
                raise _TransientProviderFailure(
                    ProviderTimeoutError("OpenSubtitles search timed out")
                ) from error
            except (aiohttp.ClientConnectionError, ConnectionResetError) as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles connection failed")
                ) from error
            except aiohttp.ClientError as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles search failed")
                ) from error
            if not isinstance(payload.get("data"), list):
                raise ProviderResponseError("OpenSubtitles search response is invalid")
            return payload

        payload = await self._retry_transient(request)
        await self._cache.set(key, payload, self._cache_ttl)
        return map_subtitles(payload, query)

    async def _download_link_request(self, file_id: int, authentication: _Authentication) -> str:
        async def request() -> str:
            try:
                async with self._session.post(
                    _api_url(authentication.api_host, "download"),
                    json={"file_id": file_id, "sub_format": "srt"},
                    headers=self._headers(token=authentication.token, json_request=True),
                ) as response:
                    if response.status == 401:
                        raise _TokenRejected
                    self._raise_transient_status(response.status, response.headers)
                    if response.status == 403:
                        raise ProviderAuthenticationError(
                            "OpenSubtitles rejected subtitle download authorization"
                        )
                    if response.status == 404:
                        raise ProviderNotFoundError("OpenSubtitles subtitle file was not found")
                    if response.status == 406:
                        raise ProviderQuotaError("OpenSubtitles download quota was rejected")
                    if response.status != 200:
                        raise ProviderResponseError("OpenSubtitles rejected the download request")
                    payload = await self._json_payload(response)
            except TimeoutError as error:
                raise _TransientProviderFailure(
                    ProviderTimeoutError("OpenSubtitles download request timed out")
                ) from error
            except (aiohttp.ClientConnectionError, ConnectionResetError) as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles connection failed")
                ) from error
            except aiohttp.ClientError as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles download request failed")
                ) from error
            link = payload.get("link")
            if not isinstance(link, str) or not link:
                raise ProviderResponseError(
                    "OpenSubtitles download response did not contain a link"
                )
            _validate_download_url(link)
            return link

        return await self._retry_transient(request)

    async def _download_link(self, file_ref: ProviderFileRef) -> str:
        try:
            file_id = int(file_ref)
        except ValueError:
            raise ProviderResponseError("OpenSubtitles file reference is invalid") from None
        if file_id < 1:
            raise ProviderResponseError("OpenSubtitles file reference is invalid")

        for authentication_attempt in range(2):
            authentication = await self._authentication_for_request()
            try:
                return await self._download_link_request(file_id, authentication)
            except _TokenRejected:
                if authentication_attempt == 1:
                    await self._invalidate_authentication(authentication.token)
                    raise ProviderAuthenticationError(
                        "OpenSubtitles rejected the refreshed authentication token"
                    ) from None
                await self._refresh_authentication(authentication.token)
        raise RuntimeError("authentication retry loop ended unexpectedly")  # pragma: no cover

    async def _download_content(self, link: str) -> bytes:
        async def request() -> bytes:
            try:
                async with self._session.get(link, allow_redirects=False) as response:
                    self._raise_transient_status(response.status, response.headers)
                    if response.status in {403, 404, 410}:
                        raise ProviderNotFoundError("OpenSubtitles temporary download link expired")
                    if response.status != 200:
                        raise ProviderResponseError("OpenSubtitles subtitle download failed")
                    if (
                        response.content_length is not None
                        and response.content_length > MAX_SUBTITLE_BYTES
                    ):
                        raise UnsafeSubtitleError("subtitle file is too large")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > MAX_SUBTITLE_BYTES:
                            raise UnsafeSubtitleError("subtitle file is too large")
                        chunks.append(chunk)
            except TimeoutError as error:
                raise _TransientProviderFailure(
                    ProviderTimeoutError("OpenSubtitles subtitle download timed out")
                ) from error
            except (aiohttp.ClientConnectionError, ConnectionResetError) as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles download connection failed")
                ) from error
            except aiohttp.ClientError as error:
                raise _TransientProviderFailure(
                    ProviderUnavailableError("OpenSubtitles subtitle download failed")
                ) from error
            return validate_srt(b"".join(chunks))

        return await self._retry_transient(request)

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle:
        if candidate.provider_id != self.provider_id:
            raise ProviderLinkError("candidate belongs to another provider")
        link = await self._download_link(candidate.provider_file_ref)
        return DownloadedSubtitle(
            content=await self._download_content(link),
            filename="subtitle.srt",
            format="srt",
            attribution=candidate.attribution,
            uploader=candidate.uploader,
        )
