"""SubDL free search and raw SRT downloads behind the existing provider port."""

from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import aiohttp

from app.core.retry import retry_async
from app.domain.errors import (
    ProviderAuthenticationError,
    ProviderLinkError,
    ProviderNotFoundError,
    ProviderQuotaError,
    ProviderResponseError,
    ProviderUnavailableError,
    UnsafeSubtitleError,
    UnsafeSubtitleLinkError,
)
from app.domain.models import EpisodeRef
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
    SubtitleQuery,
)
from app.infrastructure.providers.opensubtitles import MAX_SUBTITLE_BYTES, validate_srt


def download_url(value: str) -> str:
    try:
        url = urljoin("https://dl.subdl.com/", value)
        parsed = urlsplit(url)
        valid_port = parsed.port in {None, 443}
    except ValueError:
        raise UnsafeSubtitleLinkError("SubDL returned an unsupported download link") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "dl.subdl.com"
        or parsed.username
        or parsed.password
        or not valid_port
        or not parsed.path.startswith("/subtitle/")
        or parsed.fragment
    ):
        raise UnsafeSubtitleLinkError("SubDL returned an unsupported download link")
    if parsed.query:
        # SubDL now includes the account key in raw-file links. Free anonymous
        # downloads do not need it: discard it before storing candidates or
        # requesting the download host. Unknown/signed parameters fail closed.
        try:
            parameters = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            raise UnsafeSubtitleLinkError("SubDL returned an unsupported download link") from None
        if not parameters or any(name != "api_key" for name, _ in parameters):
            raise UnsafeSubtitleLinkError("SubDL returned an unsupported download link")
    return urlunsplit(parsed._replace(query=""))


def check_status(status: int) -> None:
    if status in {404, 410}:
        raise ProviderNotFoundError("SubDL subtitle is no longer available")
    if status in {401, 403}:
        raise ProviderAuthenticationError("SubDL rejected API access")
    if status in {402, 429}:
        raise ProviderQuotaError("SubDL quota exhausted")
    if status >= 500 or status == 408:
        raise ProviderUnavailableError("SubDL is temporarily unavailable")
    if status != 200:
        raise ProviderResponseError("SubDL request failed")


class SubdlProvider:
    provider_id = ProviderId("subdl")

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]:
        async def operation() -> list[SubtitleCandidate]:
            media = query.media
            episode = isinstance(media, EpisodeRef)
            title_id = media.series.external_id if episode else media.external_id
            params = {
                "api_key": self._api_key,
                "tmdb_id": title_id,
                "type": "tv" if episode else "movie",
                "languages": str(query.language).upper(),
                "unpack": "1",
                "subs_per_page": "30",
            }
            if episode:
                params.update(
                    season_number=str(media.season_number), episode_number=str(media.episode_number)
                )
            try:
                async with self._session.get(
                    "https://api.subdl.com/api/v1/subtitles", params=params, allow_redirects=False
                ) as response:
                    check_status(response.status)
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError):
                raise ProviderUnavailableError("SubDL connection failed") from None
            except ValueError:
                raise ProviderResponseError("SubDL returned malformed JSON") from None
            if not isinstance(payload, dict) or payload.get("status") is not True:
                raise ProviderResponseError("SubDL search failed")
            matches = payload.get("results", [])
            if not isinstance(matches, list) or not matches:
                return []
            first = matches[0]
            if (
                not isinstance(first, dict)
                or str(first.get("tmdb_id")) != title_id
                or first.get("type") != params["type"]
            ):
                return []
            subtitles = payload.get("subtitles", [])
            if not isinstance(subtitles, list):
                raise ProviderResponseError("SubDL returned invalid results")
            candidates = []
            seen = set()
            for item in subtitles:
                if not isinstance(item, dict):
                    continue
                files = item.get("unpack_files", [])
                if not isinstance(files, list):
                    continue
                for file in files:
                    if not isinstance(file, dict) or str(file.get("format", "")).lower() != "srt":
                        continue
                    if str(file.get("language", "")).upper() != params["languages"]:
                        continue
                    if episode and (
                        str(file.get("season")) != str(media.season_number)
                        or str(file.get("episode")) != str(media.episode_number)
                    ):
                        continue
                    link = file.get("url")
                    if not isinstance(link, str):
                        continue
                    try:
                        url = download_url(link)
                    except ProviderLinkError:
                        continue
                    if url in seen:
                        continue
                    seen.add(url)
                    candidates.append(
                        SubtitleCandidate(
                            self.provider_id,
                            ProviderFileRef(url),
                            query.language,
                            "srt",
                            str(
                                file.get("release_name") or item.get("release_name") or "SubDL SRT"
                            ),
                            hearing_impaired=bool(file.get("hi")),
                            attribution="Provided by SubDL",
                        )
                    )
            return candidates

        return await retry_async(operation, (ProviderUnavailableError,), attempts=3)

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle:
        if candidate.provider_id != self.provider_id:
            raise ProviderNotFoundError("Invalid subtitle provider")

        async def operation() -> DownloadedSubtitle:
            url = download_url(str(candidate.provider_file_ref))
            try:
                for _ in range(4):
                    async with self._session.get(url, allow_redirects=False) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            url = download_url(urljoin(url, response.headers.get("Location", "")))
                            continue
                        check_status(response.status)
                        if response.content_length and response.content_length > MAX_SUBTITLE_BYTES:
                            raise UnsafeSubtitleError("SubDL subtitle is too large")
                        body = bytearray()
                        async for chunk in response.content.iter_chunked(65536):
                            body.extend(chunk)
                            if len(body) > MAX_SUBTITLE_BYTES:
                                raise UnsafeSubtitleError("SubDL subtitle is too large")
                        return DownloadedSubtitle(
                            validate_srt(bytes(body), candidate.language),
                            "subdl.srt",
                            "srt",
                            "Provided by SubDL. Rights belong to the respective subtitle authors.",
                        )
                raise ProviderLinkError("SubDL redirect limit exceeded")
            except (aiohttp.ClientError, TimeoutError):
                raise ProviderUnavailableError("SubDL download connection failed") from None

        return await retry_async(operation, (ProviderUnavailableError,), attempts=3)
