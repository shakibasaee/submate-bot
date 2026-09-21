"""Deterministic OpenSubtitles request, authentication, and normalization tests."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.domain.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderLinkError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MovieRef, SeriesRef
from app.domain.subtitles import (
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
    SubtitleQuery,
)
from app.infrastructure.cache.memory import InMemoryCache
from app.infrastructure.providers.opensubtitles import OpenSubtitlesProvider, map_subtitles

LOGIN_URL = "https://api.opensubtitles.com/api/v1/login"
SEARCH_URL = "https://api.opensubtitles.com/api/v1/subtitles"
DOWNLOAD_URL = "https://api.opensubtitles.com/api/v1/download"
VIP_DOWNLOAD_URL = "https://vip-api.opensubtitles.com/api/v1/download"
TEMPORARY_LINK = "https://www.opensubtitles.com/download/test-subtitle.srt"
VALID_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


class FakeContent:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def iter_chunked(self, _size: int):
        yield self._body


@dataclass
class FakeResponse:
    status: int = 200
    payload: object = field(default_factory=dict)
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    enter_error: BaseException | None = None

    def __post_init__(self) -> None:
        self.content = FakeContent(self.body)
        self.content_length = len(self.body) if self.body else None

    async def __aenter__(self):
        await asyncio.sleep(0)
        if self.enter_error is not None:
            raise self.enter_error
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def json(self) -> object:
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


@dataclass(repr=False)
class CapturedRequest:
    method: str
    url: str
    kwargs: dict[str, Any]

    def __repr__(self) -> str:
        return f"CapturedRequest(method={self.method!r}, url={self.url!r}, kwargs=[REDACTED])"


class FakeSession:
    def __init__(
        self,
        *,
        posts: list[FakeResponse] | None = None,
        gets: list[FakeResponse] | None = None,
    ) -> None:
        self._posts = deque(posts or [])
        self._gets = deque(gets or [])
        self.requests: list[CapturedRequest] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append(CapturedRequest("POST", url, kwargs))
        if not self._posts:
            raise AssertionError(f"unexpected POST request to {url}")
        return self._posts.popleft()

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append(CapturedRequest("GET", url, kwargs))
        if not self._gets:
            raise AssertionError(f"unexpected GET request to {url}")
        return self._gets.popleft()


def login_response(token: str = "test-token", host: str = "api.opensubtitles.com") -> FakeResponse:
    return FakeResponse(payload={"token": token, "base_url": host, "status": 200, "user": {}})


def link_response(link: str = TEMPORARY_LINK) -> FakeResponse:
    return FakeResponse(
        payload={
            "link": link,
            "file_name": "test-subtitle.srt",
            "requests": 1,
            "remaining": 99,
            "message": "ok",
            "reset_time": "24 hours",
            "reset_time_utc": "2030-01-01T00:00:00Z",
        }
    )


def subtitle_response() -> FakeResponse:
    return FakeResponse(body=VALID_SRT)


def search_response() -> FakeResponse:
    return FakeResponse(
        payload={
            "data": [
                {
                    "attributes": {
                        "files": [{"file_id": 123, "file_name": "film.srt"}],
                        "release": "WEBRip",
                        "download_count": 20,
                        "ratings": 8.5,
                    }
                }
            ],
            "page": 1,
            "total_pages": 1,
            "total_count": 1,
        }
    )


def candidate(file_ref: str = "123") -> SubtitleCandidate:
    return SubtitleCandidate(
        ProviderId("opensubtitles"),
        ProviderFileRef(file_ref),
        LanguageCode.ENGLISH,
        "srt",
        "WEBRip",
        attribution="OpenSubtitles",
    )


def provider(
    session: FakeSession,
    *,
    api_key: str = "test-api-key",
    username: str | None = "test-user",
    password: str | None = "test-password",
) -> OpenSubtitlesProvider:
    return OpenSubtitlesProvider(
        session,  # type: ignore[arg-type]
        api_key,
        InMemoryCache(),
        username=username,
        password=password,
        retry_base_delay=0,
        retry_jitter=0,
    )


def requests_for(session: FakeSession, url: str) -> list[CapturedRequest]:
    return [request for request in session.requests if request.url == url]


def test_movie_search_uses_api_key_and_exact_tmdb_id() -> None:
    session = FakeSession(gets=[search_response()])

    results = asyncio.run(
        provider(session).search(
            SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
        )
    )

    request = session.requests[0]
    assert (request.method, request.url) == ("GET", SEARCH_URL)
    assert request.kwargs["params"] == {"tmdb_id": 27205, "languages": "en"}
    assert request.kwargs["headers"]["Api-Key"] == "test-api-key"
    assert "Authorization" not in request.kwargs["headers"]
    assert [item.provider_file_ref for item in results] == ["123"]


def test_episode_search_uses_episode_and_parent_tmdb_ids() -> None:
    session = FakeSession(gets=[search_response()])
    episode = EpisodeRef("62085", SeriesRef("1396", "Breaking Bad"), 2, 5, "Breakage")

    asyncio.run(provider(session).search(SubtitleQuery(episode, LanguageCode.PERSIAN)))

    assert session.requests[0].kwargs["params"] == {
        "tmdb_id": 62085,
        "parent_tmdb_id": 1396,
        "season_number": 2,
        "episode_number": 5,
        "languages": "fa",
    }


def test_successful_login_and_download_match_the_provider_contract() -> None:
    session = FakeSession(posts=[login_response(), link_response()], gets=[subtitle_response()])

    downloaded = asyncio.run(provider(session).download(candidate()))

    login = requests_for(session, LOGIN_URL)[0]
    assert login.method == "POST"
    assert login.kwargs["json"] == {"username": "test-user", "password": "test-password"}
    assert login.kwargs["headers"] == {
        "Api-Key": "test-api-key",
        "User-Agent": "subtitle-telegram-bot v0.1",
        "Content-Type": "application/json",
    }
    download = requests_for(session, DOWNLOAD_URL)[0]
    assert download.method == "POST"
    assert download.kwargs["json"] == {"file_id": 123, "sub_format": "srt"}
    assert download.kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert session.requests[-1].kwargs == {"allow_redirects": False}
    assert downloaded.content == VALID_SRT
    assert downloaded.attribution == "OpenSubtitles"


def test_bearer_token_is_reused_without_another_login() -> None:
    session = FakeSession(
        posts=[login_response(), link_response(), link_response()],
        gets=[subtitle_response(), subtitle_response()],
    )
    adapter = provider(session)

    async def scenario() -> None:
        await adapter.download(candidate())
        await adapter.download(candidate())

    asyncio.run(scenario())

    assert len(requests_for(session, LOGIN_URL)) == 1
    assert len(requests_for(session, DOWNLOAD_URL)) == 2


def test_concurrent_protected_requests_share_one_login() -> None:
    session = FakeSession(
        posts=[login_response(), *[link_response() for _ in range(5)]],
        gets=[subtitle_response() for _ in range(5)],
    )
    adapter = provider(session)

    async def scenario() -> None:
        await asyncio.gather(*[adapter.download(candidate()) for _ in range(5)])

    asyncio.run(scenario())

    assert len(requests_for(session, LOGIN_URL)) == 1
    assert len(requests_for(session, DOWNLOAD_URL)) == 5


def test_expired_token_causes_one_login_and_one_request_retry() -> None:
    session = FakeSession(
        posts=[
            login_response("old-token"),
            FakeResponse(status=401),
            login_response("new-token"),
            link_response(),
        ],
        gets=[subtitle_response()],
    )

    asyncio.run(provider(session).download(candidate()))

    assert len(requests_for(session, LOGIN_URL)) == 2
    download_requests = requests_for(session, DOWNLOAD_URL)
    assert len(download_requests) == 2
    assert [request.kwargs["headers"]["Authorization"] for request in download_requests] == [
        "Bearer old-token",
        "Bearer new-token",
    ]


def test_failed_reauthentication_is_not_retried_indefinitely() -> None:
    session = FakeSession(
        posts=[
            login_response("expired-token"),
            FakeResponse(status=401),
            FakeResponse(status=401),
        ]
    )

    with pytest.raises(ProviderAuthenticationError) as captured:
        asyncio.run(provider(session).download(candidate()))

    assert len(requests_for(session, LOGIN_URL)) == 2
    assert len(requests_for(session, DOWNLOAD_URL)) == 1
    assert "expired-token" not in str(captured.value)


def test_refreshed_token_rejection_stops_after_one_original_request_retry() -> None:
    session = FakeSession(
        posts=[
            login_response("expired-token"),
            FakeResponse(status=401),
            login_response("rejected-token"),
            FakeResponse(status=401),
        ]
    )

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(provider(session).download(candidate()))

    assert len(requests_for(session, LOGIN_URL)) == 2
    assert len(requests_for(session, DOWNLOAD_URL)) == 2


def test_login_rejects_invalid_credentials_without_transient_retry() -> None:
    session = FakeSession(posts=[FakeResponse(status=403)])

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(provider(session).download(candidate()))

    assert len(requests_for(session, LOGIN_URL)) == 1


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(payload={}),
        FakeResponse(payload={"token": 123, "base_url": "api.opensubtitles.com"}),
        FakeResponse(payload=ValueError("invalid JSON")),
    ],
)
def test_malformed_login_response_is_normalized(response: FakeResponse) -> None:
    session = FakeSession(posts=[response])

    with pytest.raises(ProviderResponseError):
        asyncio.run(provider(session).download(candidate()))

    assert len(session.requests) == 1


def test_login_selected_host_is_allowlisted_and_used_for_download() -> None:
    session = FakeSession(
        posts=[login_response(host="vip-api.opensubtitles.com"), link_response()],
        gets=[subtitle_response()],
    )

    asyncio.run(provider(session).download(candidate()))

    assert len(requests_for(session, VIP_DOWNLOAD_URL)) == 1


@pytest.mark.parametrize(
    "host",
    [
        "https://api.opensubtitles.com/api/v1",
        "api.opensubtitles.com.attacker.example",
        "api.opensubtitles.com/path",
        " api.opensubtitles.com",
        "",
    ],
)
def test_login_rejects_malformed_or_unapproved_api_hosts(host: str) -> None:
    session = FakeSession(posts=[login_response(host=host)])

    with pytest.raises(ProviderResponseError):
        asyncio.run(provider(session).download(candidate()))

    assert len(session.requests) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_search_normalizes_authentication_failures(status: int) -> None:
    session = FakeSession(gets=[FakeResponse(status=status)])

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )

    assert len(session.requests) == 1


def test_search_normalizes_not_found() -> None:
    session = FakeSession(gets=[FakeResponse(status=404)])

    with pytest.raises(ProviderNotFoundError):
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )


def test_rate_limit_is_retried_three_times_and_preserves_retry_after() -> None:
    session = FakeSession(
        gets=[FakeResponse(status=429, headers={"Retry-After": "7"}) for _ in range(3)]
    )

    with pytest.raises(ProviderRateLimitError) as captured:
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )

    assert captured.value.retry_after == 7
    assert len(session.requests) == 3


@pytest.mark.parametrize("status", [500, 502])
def test_selected_server_failures_are_bounded_and_normalized(status: int) -> None:
    session = FakeSession(gets=[FakeResponse(status=status) for _ in range(3)])

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )

    assert len(session.requests) == 3


def test_transient_server_failures_can_recover_within_retry_limit() -> None:
    session = FakeSession(
        gets=[FakeResponse(status=500), FakeResponse(status=502), search_response()]
    )

    results = asyncio.run(
        provider(session).search(
            SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
        )
    )

    assert len(results) == 1
    assert len(session.requests) == 3


def test_timeout_is_bounded_and_normalized() -> None:
    session = FakeSession(gets=[FakeResponse(enter_error=TimeoutError()) for _ in range(3)])

    with pytest.raises(ProviderTimeoutError) as captured:
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )

    assert len(session.requests) == 3
    assert captured.value.__cause__ is None


def test_connection_reset_is_bounded_and_normalized() -> None:
    session = FakeSession(gets=[FakeResponse(enter_error=ConnectionResetError()) for _ in range(3)])

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )

    assert len(session.requests) == 3


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(payload=ValueError("invalid JSON")),
        FakeResponse(payload={"unexpected": []}),
        FakeResponse(payload=[]),
        FakeResponse(status=400),
    ],
)
def test_malformed_or_rejected_search_responses_are_normalized(response: FakeResponse) -> None:
    session = FakeSession(gets=[response])

    with pytest.raises(ProviderResponseError):
        asyncio.run(
            provider(session).search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )

    assert len(session.requests) == 1


def test_missing_provider_configuration_fails_only_when_required() -> None:
    search_session = FakeSession()
    download_session = FakeSession()
    search_adapter = provider(search_session, api_key="")
    download_adapter = provider(download_session, username=None, password=None)

    with pytest.raises(ProviderConfigurationError, match="API key"):
        asyncio.run(
            search_adapter.search(
                SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH)
            )
        )
    with pytest.raises(ProviderConfigurationError, match="username and password"):
        asyncio.run(download_adapter.download(candidate()))

    assert search_session.requests == []
    assert download_session.requests == []


def test_download_rejects_invalid_file_reference_before_authentication() -> None:
    session = FakeSession()

    with pytest.raises(ProviderResponseError, match="file reference"):
        asyncio.run(provider(session).download(candidate("missing")))

    assert session.requests == []


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (FakeResponse(status=403), ProviderAuthenticationError),
        (FakeResponse(status=404), ProviderNotFoundError),
        (FakeResponse(status=400), ProviderResponseError),
        (FakeResponse(payload={"file_name": "missing-link.srt"}), ProviderResponseError),
    ],
)
def test_download_link_rejections_are_normalized(
    response: FakeResponse, error_type: type[Exception]
) -> None:
    session = FakeSession(posts=[login_response(), response])

    with pytest.raises(error_type):
        asyncio.run(provider(session).download(candidate()))


def test_unsafe_temporary_download_host_is_rejected() -> None:
    session = FakeSession(
        posts=[login_response(), link_response("https://attacker.example/subtitle.srt")]
    )

    with pytest.raises(ProviderLinkError):
        asyncio.run(provider(session).download(candidate()))

    assert not any(
        request.url.startswith("https://attacker.example") for request in session.requests
    )


def test_malformed_temporary_download_url_is_normalized() -> None:
    session = FakeSession(
        posts=[login_response(), link_response("https://opensubtitles.com:invalid/file.srt")]
    )

    with pytest.raises(ProviderLinkError):
        asyncio.run(provider(session).download(candidate()))


def test_expired_temporary_download_is_normalized_as_not_found() -> None:
    session = FakeSession(
        posts=[login_response(), link_response()],
        gets=[FakeResponse(status=404)],
    )

    with pytest.raises(ProviderNotFoundError):
        asyncio.run(provider(session).download(candidate()))


def test_all_provider_files_are_normalized_and_missing_ids_are_skipped() -> None:
    payload: dict[str, object] = {
        "data": [
            {
                "attributes": {
                    "files": [
                        {"file_id": 1, "file_name": "film.srt"},
                        {"file_id": 2, "file_name": "film-forced.srt"},
                        {"file_name": "missing-id.srt"},
                    ],
                    "release": "WEBRip",
                    "foreign_parts_only": True,
                    "hearing_impaired": False,
                    "download_count": 20,
                    "ratings": 8.5,
                    "uploader": {"name": "trusted"},
                }
            }
        ]
    }
    results = map_subtitles(
        payload,
        SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH),
    )

    assert [item.provider_file_ref for item in results] == ["1", "2"]
    assert all(item.provider_id == ProviderId("opensubtitles") for item in results)
    assert all(item.forced for item in results)
    assert results[0].uploader == "trusted"
