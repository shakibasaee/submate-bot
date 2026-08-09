"""Tests for TMDb result mapping and callback validation."""

import asyncio
from unittest.mock import AsyncMock

from app.bot.handlers.search import (
    episodes_keyboard,
    result_label,
    results_keyboard,
    seasons_keyboard,
    title_selected,
)
from app.bot.state import Episode, MediaType, SearchResult, Season, conversation_store
from app.services.tmdb import map_episodes, map_search_results, map_seasons


class User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class MessageStub:
    def __init__(self) -> None:
        self.answer = AsyncMock()


class CallbackStub:
    def __init__(self, user_id: int, data: str) -> None:
        self.from_user = User(user_id)
        self.data = data
        self.message = MessageStub()
        self.answer = AsyncMock()


def test_map_search_results_combines_movies_and_tv_and_limits_results() -> None:
    payload = {
        "results": [
            {"id": 1, "media_type": "movie", "title": "Inception", "release_date": "2010-07-16"},
            {"id": 2, "media_type": "tv", "name": "Inception", "first_air_date": "2018-01-01"},
            {"id": 3, "media_type": "person", "name": "Ignored"},
            {"id": 4, "media_type": "movie", "title": "No date"},
        ]
    }

    results = map_search_results(payload, limit=2)

    assert [(result.media_type, result.title, result.year) for result in results] == [
        (MediaType.MOVIE, "Inception", "2010"),
        (MediaType.TV, "Inception", "2018"),
    ]


def test_result_buttons_include_type_year_and_callback_data() -> None:
    result = SearchResult(27205, MediaType.MOVIE, "Inception", "2010")

    keyboard = results_keyboard([result], workflow_id=3)

    assert result_label(result) == "🎬 Inception (2010)"
    assert keyboard.inline_keyboard[0][0].callback_data == "title:3:movie:27205"


def test_seasons_exclude_specials_and_episodes_keep_actual_numbers() -> None:
    seasons = map_seasons(
        {
            "seasons": [
                {"season_number": 0, "name": "Specials"},
                {"season_number": 2, "name": "Season 2"},
            ]
        }
    )
    episodes = map_episodes(
        {
            "episodes": [
                {"episode_number": 1, "name": "Pilot"},
                {"episode_number": 3, "name": "Finale"},
            ]
        }
    )

    assert seasons == [Season(2, "Season 2")]
    assert episodes == [Episode(1, "Pilot"), Episode(3, "Finale")]
    assert seasons_keyboard(seasons, 3).inline_keyboard[0][0].callback_data == "season:3:2"
    assert episodes_keyboard(2, episodes, 3).inline_keyboard[0][1].callback_data == (
        "episode:3:2:3"
    )


def test_episode_selection_keeps_exact_tmdb_series_season_and_episode_identifiers() -> None:
    conversation_store._conversations.clear()
    conversation = conversation_store.get(9)
    conversation.selected_tmdb_id = 1396
    conversation.selected_media_type = MediaType.TV
    workflow_id = conversation.workflow_id
    conversation_store.set_seasons(9, workflow_id, [Season(4, "Season 4")])
    assert conversation_store.select_season(9, workflow_id, 4) == Season(4, "Season 4")
    conversation_store.set_episodes(9, workflow_id, [Episode(2, "Episode Two")])

    assert conversation_store.select_episode(9, workflow_id, 4, 2) == Episode(2, "Episode Two")
    assert (
        conversation.selected_tmdb_id,
        conversation.selected_season_number,
        conversation.selected_episode_number,
    ) == (1396, 4, 2)


def test_invalid_title_callback_is_rejected() -> None:
    callback = CallbackStub(1, "title:0:movie:not-an-id")

    asyncio.run(title_selected(callback))

    assert callback.answer.await_args.args[0] == "That title selection is invalid."
    assert callback.answer.await_args.kwargs["show_alert"] is True


def test_callback_must_match_the_users_latest_search_results() -> None:
    conversation_store._conversations.clear()
    visible = SearchResult(27205, MediaType.MOVIE, "Inception", "2010")
    workflow_id = conversation_store.get(1).workflow_id
    conversation_store.set_search_results(1, workflow_id, [visible])
    callback = CallbackStub(1, f"title:{workflow_id}:tv:27205")

    asyncio.run(title_selected(callback))

    assert callback.answer.await_args.args[0] == "That result has expired. Search again."
    assert conversation_store.get(1).selected_tmdb_id is None


def test_valid_callback_stores_tmdb_id_and_media_type() -> None:
    conversation_store._conversations.clear()
    visible = SearchResult(27205, MediaType.MOVIE, "Inception", "2010")
    workflow_id = conversation_store.get(1).workflow_id
    conversation_store.set_search_results(1, workflow_id, [visible])
    callback = CallbackStub(1, f"title:{workflow_id}:movie:27205")

    asyncio.run(title_selected(callback))

    conversation = conversation_store.get(1)
    assert conversation.selected_tmdb_id == 27205
    assert conversation.selected_media_type is MediaType.MOVIE
