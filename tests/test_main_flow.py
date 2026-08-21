"""Application-level movie and television flows without Telegram objects."""

import asyncio

from app.domain.languages import LanguageCode
from app.domain.models import (
    EpisodeRef,
    MediaSearchResult,
    MediaType,
    MovieRef,
    SeasonSummary,
    SeriesRef,
)
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
)
from tests.support import FakeMetadata, FakeProvider, build_test_application

VALID_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def candidate(language: LanguageCode) -> SubtitleCandidate:
    return SubtitleCandidate(
        provider_id=ProviderId("fake"),
        provider_file_ref=ProviderFileRef("same-id"),
        language=language,
        format="srt",
        release_name="WEB-DL",
        rating=8.5,
        attribution="Fake provider",
    )


def test_movie_flow_reaches_provider_neutral_delivery() -> None:
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("27205", MediaType.MOVIE, "Inception", "2010")]
    )
    provider = FakeProvider(
        candidates=[candidate(LanguageCode.ENGLISH)],
        downloaded=DownloadedSubtitle(VALID_SRT, "provider.srt", "srt", "Fake provider"),
    )
    app = build_test_application(metadata=metadata, provider=provider)

    async def flow() -> None:
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(1, "Inception")
        selected = await app.services.select_title.execute(
            1, search.workflow_id, MediaType.MOVIE, "27205"
        )
        assert isinstance(selected.selected, MovieRef)
        assert selected.subtitle_page is not None
        delivery = await app.services.deliver_subtitle.execute(
            1, search.workflow_id, ProviderId("fake"), 0
        )
        assert delivery.subtitle.filename == "Inception-en.srt"
        assert delivery.subtitle.content == VALID_SRT

    asyncio.run(flow())
    assert isinstance(provider.search_queries[0].media, MovieRef)
    assert provider.download_calls == 1


def test_tv_flow_requires_and_preserves_exact_season_episode_coordinates() -> None:
    series = SeriesRef("1396", "Example Series", "2008")
    episode = EpisodeRef(series, 2, 5, "Episode Five")
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("1396", MediaType.TV, series.title, series.year)],
        season_results=[SeasonSummary(2, "Season 2")],
        episode_results=[episode],
    )
    provider = FakeProvider(candidates=[candidate(LanguageCode.PERSIAN)])
    app = build_test_application(metadata=metadata, provider=provider)

    async def flow() -> None:
        await app.services.choose_language.execute(2, LanguageCode.PERSIAN)
        search = await app.services.search_titles.execute(2, "Example Series")
        title = await app.services.select_title.execute(2, search.workflow_id, MediaType.TV, "1396")
        assert title.seasons == (SeasonSummary(2, "Season 2"),)
        episodes = await app.services.navigate_series.select_season(2, search.workflow_id, 2)
        assert episodes.episodes == (episode,)
        selected = await app.services.navigate_series.select_episode(2, search.workflow_id, 2, 5)
        assert selected.episode == episode

    asyncio.run(flow())
    query = provider.search_queries[0]
    assert isinstance(query.media, EpisodeRef)
    assert (query.media.season_number, query.media.episode_number) == (2, 5)
