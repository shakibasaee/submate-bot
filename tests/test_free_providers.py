"""Explicit demos and safe free-provider integration without network calls."""

import asyncio

import pytest

from app.bootstrap import build_runtime
from app.core.config import Settings
from app.domain.errors import (
    ProviderAuthenticationError,
    ProviderLinkError,
    ProviderQuotaError,
    ProviderUnavailableError,
    UnsafeSubtitleError,
)
from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MovieRef, SeriesRef
from app.domain.subtitles import ProviderFileRef, ProviderId, SubtitleCandidate, SubtitleQuery
from app.infrastructure.providers.demo import DemoSubtitleProvider
from app.infrastructure.providers.opensubtitles import validate_srt
from app.infrastructure.providers.subdl import SubdlProvider, download_url
from scripts.production_smoke import providers_are_configured
from tests.test_opensubtitles import VALID_SRT, FakeResponse, FakeSession

QUERY = SubtitleQuery(MovieRef("27205", "Inception", "2010"), LanguageCode.ENGLISH)


def test_demo_is_original_valid_srt_and_retry_succeeds():
    async def scenario():
        provider = DemoSubtitleProvider()
        choices = await provider.search(QUERY)
        assert all("DEMO" in item.release_name for item in choices)
        normal = await provider.download(choices[0])
        assert validate_srt(normal.content)
        assert "not a movie subtitle" in normal.content.decode()
        with pytest.raises(ProviderUnavailableError):
            await provider.download(choices[1])
        assert (await provider.download(choices[1])).content == normal.content
        persian = await provider.search(SubtitleQuery(QUERY.media, LanguageCode.PERSIAN))
        assert "آزمایش" in (await provider.download(persian[0])).content.decode()

    asyncio.run(scenario())


def test_demo_composition_is_explicit_and_not_production_verified():
    settings = Settings(
        _env_file=None,
        telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz",
        tmdb_api_key="fake-key",
        demo_mode=True,
    )

    async def scenario():
        runtime = await build_runtime(settings)
        try:
            assert list(runtime.services.deliver_subtitle._providers) == ["demo"]
            assert not providers_are_configured(settings)
        finally:
            await runtime.close()
        assert runtime.http_session.closed

    asyncio.run(scenario())


def payload(*, episode=1, language="EN", url="/subtitle/parent/raw"):
    return {
        "status": True,
        "results": [{"tmdb_id": 1396, "type": "tv"}],
        "subtitles": [
            {
                "release_name": "WEB",
                "unpack_files": [
                    {
                        "format": "srt",
                        "language": language,
                        "season": 1,
                        "episode": episode,
                        "url": url,
                        "release_name": "WEB-DL",
                    }
                ],
            }
        ],
    }


def test_subdl_episode_coordinates_language_and_raw_download():
    session = FakeSession(gets=[FakeResponse(payload=payload()), FakeResponse(body=VALID_SRT)])
    provider = SubdlProvider(session, "test-api-key")
    query = SubtitleQuery(
        EpisodeRef("62085", SeriesRef("1396", "Breaking Bad"), 1, 1, "Pilot"), LanguageCode.ENGLISH
    )

    async def scenario():
        choices = await provider.search(query)
        assert len(choices) == 1
        result = await provider.download(choices[0])
        assert result.content == VALID_SRT
        assert "api_key" not in session.requests[1].kwargs.get("params", {})

    asyncio.run(scenario())
    params = session.requests[0].kwargs["params"]
    assert params["tmdb_id"] == "1396"
    assert params["season_number"] == "1" and params["episode_number"] == "1"
    assert session.requests[1].kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "data",
    [
        payload(episode=2),
        payload(language="FA"),
        payload(url="https://evil.example/subtitle/file"),
        {"status": True, "results": [{"tmdb_id": 999, "type": "tv"}], "subtitles": []},
    ],
)
def test_subdl_rejects_mismatched_or_unsafe_results(data):
    provider = SubdlProvider(FakeSession(gets=[FakeResponse(payload=data)]), "test-key")
    query = SubtitleQuery(
        EpisodeRef("62085", SeriesRef("1396", "Breaking Bad"), 1, 1, "Pilot"), LanguageCode.ENGLISH
    )
    assert asyncio.run(provider.search(query)) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://dl.subdl.com/subtitle/file",
        "https://evil.example/subtitle/file",
        "https://dl.subdl.com:invalid/subtitle/file",
        "https://[invalid/subtitle/file",
        "https://user:pass@dl.subdl.com/subtitle/file",
        "https://dl.subdl.com/subtitle/file?redirect=https://evil.example",
        "https://dl.subdl.com/subtitle/file?api_key=x&signature=unknown",
        "https://dl.subdl.com/subtitle/file?api_key",
    ],
)
def test_subdl_download_host_validation(url):
    with pytest.raises(ProviderLinkError):
        download_url(url)


def test_subdl_account_key_in_raw_links_is_discarded_before_storage_and_download():
    data = payload(url="https://dl.subdl.com/subtitle/parent/raw?api_key=private-example")
    data["results"] = [{"tmdb_id": 27205, "type": "movie"}]
    session = FakeSession(gets=[FakeResponse(payload=data), FakeResponse(body=VALID_SRT)])
    provider = SubdlProvider(session, "test-api-key")

    async def scenario():
        choices = await provider.search(QUERY)
        assert len(choices) == 1
        assert str(choices[0].provider_file_ref) == "https://dl.subdl.com/subtitle/parent/raw"
        await provider.download(choices[0])

    asyncio.run(scenario())
    assert "api_key" not in session.requests[1].url
    assert "params" not in session.requests[1].kwargs


@pytest.mark.parametrize(
    "status,error", [(401, ProviderAuthenticationError), (429, ProviderQuotaError)]
)
def test_subdl_auth_and_quota_do_not_retry(status, error):
    session = FakeSession(gets=[FakeResponse(status=status)])
    with pytest.raises(error):
        asyncio.run(SubdlProvider(session, "test-key").search(QUERY))
    assert len(session.requests) == 1


def test_subdl_retries_outage_only_three_times():
    session = FakeSession(gets=[FakeResponse(status=503) for _ in range(3)])
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(SubdlProvider(session, "test-key").search(QUERY))
    assert len(session.requests) == 3


def test_subdl_rejects_html_and_cross_host_redirects():
    candidate = SubtitleCandidate(
        ProviderId("subdl"),
        ProviderFileRef("/subtitle/test/raw"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB",
    )
    for response, expected in [
        (FakeResponse(body=b"<html>not subtitles</html>"), UnsafeSubtitleError),
        (
            FakeResponse(status=302, headers={"Location": "https://evil.example/steal"}),
            ProviderLinkError,
        ),
    ]:
        with pytest.raises(expected):
            asyncio.run(SubdlProvider(FakeSession(gets=[response]), "test-key").download(candidate))


def test_subdl_movie_uses_movie_tmdb_id_and_excludes_zip_only_entries():
    data = payload()
    data["results"] = [{"tmdb_id": 27205, "type": "movie"}]
    data["subtitles"].append({"url": "/subtitle/archive.zip"})
    session = FakeSession(gets=[FakeResponse(payload=data)])
    choices = asyncio.run(SubdlProvider(session, "test-key").search(QUERY))
    assert len(choices) == 1
    assert session.requests[0].kwargs["params"]["type"] == "movie"
    assert "episode_number" not in session.requests[0].kwargs["params"]


@pytest.mark.parametrize("tv", [False, True])
def test_demo_application_failure_retry_and_next_search(tv):
    from app.domain.models import MediaSearchResult, MediaType, SeasonSummary
    from tests.support import FakeMetadata, build_test_application

    series = SeriesRef("1396", "Breaking Bad")
    episode = EpisodeRef("62085", series, 1, 1, "Pilot")
    metadata = FakeMetadata(
        search_results=[
            MediaSearchResult(
                "1396" if tv else "27205",
                MediaType.TV if tv else MediaType.MOVIE,
                "Breaking Bad" if tv else "Inception",
            )
        ],
        season_results=[SeasonSummary(1, "Season 1")],
        episode_results=[episode],
    )
    app = build_test_application(metadata=metadata, provider=DemoSubtitleProvider())

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        found = await app.services.search_titles.execute(1, "Breaking Bad" if tv else "Inception")
        await app.services.select_title.execute(
            1, found.workflow_id, MediaType.TV if tv else MediaType.MOVIE, "1396" if tv else "27205"
        )
        if tv:
            await app.services.navigate_series.select_season(1, found.workflow_id, 1)
            await app.services.navigate_series.select_episode(1, found.workflow_id, 1, 1)
        current = await app.conversations.get(1)
        index = next(
            i
            for i, item in enumerate(current.subtitle_candidates)
            if str(item.provider_file_ref).startswith("retry-")
        )
        with pytest.raises(ProviderUnavailableError):
            await app.services.deliver_subtitle.execute(
                1, found.workflow_id, ProviderId("demo"), index
            )
        recovery = await app.services.deliver_subtitle.recovery_page(1, found.workflow_id)
        delivered = await app.services.deliver_subtitle.execute(
            1, recovery.workflow_id, ProviderId("demo"), index
        )
        assert validate_srt(delivered.subtitle.content)
        assert "DEMO" in delivered.subtitle.attribution
        if tv:
            assert "S01E01" in delivered.subtitle.filename
        await app.services.deliver_subtitle.finish(1, recovery.workflow_id)
        await app.services.start_search.execute(1)
        assert (await app.services.search_titles.execute(1, "another title")).results

    asyncio.run(scenario())
