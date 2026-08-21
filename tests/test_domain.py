"""Construction, validation, and equality of provider-neutral domain models."""

import pytest

from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MovieRef, SeasonSummary, SeriesRef
from app.domain.subtitles import ProviderFileRef, ProviderId, SubtitleCandidate, SubtitleQuery


def test_movie_and_episode_queries_are_distinct_complete_types() -> None:
    movie_query = SubtitleQuery(MovieRef("1", "Movie"), LanguageCode.ENGLISH)
    series = SeriesRef("2", "Series")
    episode_query = SubtitleQuery(EpisodeRef(series, 2, 5, "Episode"), LanguageCode.PERSIAN)
    assert isinstance(movie_query.media, MovieRef)
    assert isinstance(episode_query.media, EpisodeRef)
    assert episode_query.media.season_number == 2
    with pytest.raises(ValueError):
        EpisodeRef(series, 0, 5, "Invalid")


def test_candidates_use_opaque_provider_scoped_references_and_value_equality() -> None:
    first = SubtitleCandidate(
        ProviderId("first"),
        ProviderFileRef("same-file"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB-DL",
    )
    duplicate = SubtitleCandidate(
        ProviderId("first"),
        ProviderFileRef("same-file"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB-DL",
    )
    second_provider = SubtitleCandidate(
        ProviderId("second"),
        ProviderFileRef("same-file"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB-DL",
    )
    assert first == duplicate
    assert first != second_provider
    assert first.callback_key != second_provider.callback_key


def test_season_numbers_must_be_positive() -> None:
    assert SeasonSummary(1, "Season 1") == SeasonSummary(1, "Season 1")
    with pytest.raises(ValueError):
        SeasonSummary(0, "Specials")
