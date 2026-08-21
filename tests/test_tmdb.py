"""TMDb normalization and Telegram keyboard tests."""

from app.bot.keyboards.media import episodes_keyboard, result_label, results_keyboard
from app.domain.models import MediaSearchResult, MediaType, SeriesRef, WorkflowId
from app.infrastructure.metadata.tmdb import map_episodes, map_search_results, map_seasons


def test_map_search_results_combines_movies_and_tv_and_limits_results() -> None:
    payload: dict[str, object] = {
        "results": [
            {"id": 1, "media_type": "movie", "title": "Inception", "release_date": "2010"},
            {"id": 2, "media_type": "tv", "name": "Series", "first_air_date": "2018"},
            {"id": 3, "media_type": "person", "name": "Ignored"},
        ]
    }
    results = map_search_results(payload)
    assert [(item.external_id, item.media_type) for item in results] == [
        ("1", MediaType.MOVIE),
        ("2", MediaType.TV),
    ]


def test_season_zero_is_excluded_and_episode_numbers_are_preserved() -> None:
    seasons = map_seasons(
        {"seasons": [{"season_number": 0, "name": "Specials"}, {"season_number": 2, "name": "S2"}]}
    )
    series = SeriesRef("2", "Series")
    episodes = map_episodes(
        {"season_number": 2, "episodes": [{"episode_number": 3, "name": "Finale"}]},
        series,
    )
    assert [item.number for item in seasons] == [2]
    assert [(item.season_number, item.episode_number) for item in episodes] == [(2, 3)]


def test_callback_data_carries_opaque_workflow_and_external_ids() -> None:
    workflow_id = WorkflowId("workflow-token")
    result = MediaSearchResult("movie-ref", MediaType.MOVIE, "Inception", "2010")
    keyboard = results_keyboard([result], workflow_id)
    assert result_label(result) == "🎬 Inception (2010)"
    assert keyboard.inline_keyboard[0][0].callback_data == ("title:workflow-token:movie:movie-ref")
    episode_keyboard = episodes_keyboard(2, (1, 3), workflow_id)
    assert episode_keyboard.inline_keyboard[0][1].callback_data == ("episode:workflow-token:2:3")
