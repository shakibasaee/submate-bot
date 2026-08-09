"""Regression tests for cancellation, stale callbacks, rendering, and duplicate clicks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import Message

from app.bot.handlers import subtitle as subtitle_handler
from app.bot.handlers.search import (
    episode_selected,
    result_label,
    season_selected,
    title_selected,
)
from app.bot.handlers.subtitle import subtitle_label, subtitle_selected
from app.bot.presentation import (
    TELEGRAM_BUTTON_TEXT_LIMIT,
    TELEGRAM_CAPTION_LIMIT,
    safe_caption,
    safe_html_text,
)
from app.bot.state import (
    ConversationStore,
    Episode,
    MediaType,
    SearchResult,
    Season,
    SubtitleLanguage,
    SubtitleResult,
    conversation_store,
)


class User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


def test_cancel_invalidates_every_ephemeral_selection_and_old_async_result() -> None:
    store = ConversationStore()
    user_id = 7
    store.choose_language(user_id, SubtitleLanguage.PERSIAN)
    workflow_id = store.get(user_id).workflow_id
    title = SearchResult(1396, MediaType.TV, "Series", "2008")
    subtitle = SubtitleResult(42, "WEB-DL", "srt", False, 1, 8.0, "user")

    assert store.set_search_results(user_id, workflow_id, [title])
    assert store.select_result(user_id, workflow_id, MediaType.TV, 1396) == title
    assert store.set_seasons(user_id, workflow_id, [Season(2, "Season 2")])
    assert store.select_season(user_id, workflow_id, 2) is not None
    assert store.set_episodes(user_id, workflow_id, [Episode(5, "Episode 5")])
    assert store.select_episode(user_id, workflow_id, 2, 5) is not None
    assert store.set_subtitle_results(user_id, workflow_id, [subtitle])

    store.cancel(user_id)

    conversation = store.get(user_id)
    assert conversation.language is SubtitleLanguage.PERSIAN
    assert not store.is_active(user_id, workflow_id)
    assert store.select_subtitle(user_id, workflow_id, 42) is None
    assert not store.set_subtitle_results(user_id, workflow_id, [subtitle])
    assert conversation.selected_tmdb_id is None
    assert conversation.selected_season_number is None
    assert conversation.selected_episode_number is None
    assert conversation.subtitle_results is None


def test_cancelled_title_season_episode_and_subtitle_callbacks_are_expired() -> None:
    conversation_store._conversations.clear()
    user_id = 8
    conversation_store.choose_language(user_id, SubtitleLanguage.ENGLISH)
    old_workflow_id = conversation_store.get(user_id).workflow_id
    conversation_store.cancel(user_id)

    async def assert_all_callbacks_expired() -> None:
        callbacks = [
            (title_selected, f"title:{old_workflow_id}:movie:1"),
            (season_selected, f"season:{old_workflow_id}:1"),
            (episode_selected, f"episode:{old_workflow_id}:1:1"),
            (subtitle_selected, f"subtitle:{old_workflow_id}:1"),
        ]
        for handler, data in callbacks:
            callback = SimpleNamespace(
                from_user=User(user_id),
                data=data,
                answer=AsyncMock(),
                message=None,
            )
            await handler(callback)  # type: ignore[arg-type]
            callback.answer.assert_awaited_once()
            assert "expired" in callback.answer.await_args.args[0].lower()

    asyncio.run(assert_all_callbacks_expired())


def test_external_html_is_escaped_and_telegram_text_is_bounded() -> None:
    assert safe_html_text("<b>Test</b> & broken <") == ("&lt;b&gt;Test&lt;/b&gt; &amp; broken &lt;")

    title = SearchResult(1, MediaType.MOVIE, "<b>" + "x" * 200, "2025")
    subtitle = SubtitleResult(
        2,
        "<i>" + "release" * 100,
        "srt",
        True,
        100,
        9.5,
        "uploader",
    )
    assert len(result_label(title)) <= TELEGRAM_BUTTON_TEXT_LIMIT
    assert len(subtitle_label(subtitle)) <= TELEGRAM_BUTTON_TEXT_LIMIT

    caption = safe_caption("Uploader: <b>bad</b> " + "x" * 2000)
    assert len(caption) <= TELEGRAM_CAPTION_LIMIT
    assert "<b>" not in caption
    assert "&lt;b&gt;bad&lt;/b&gt;" in caption


def test_rapid_duplicate_subtitle_callbacks_start_only_one_delivery(
    monkeypatch,
) -> None:
    conversation_store._conversations.clear()
    user_id = 19
    conversation_store.choose_language(user_id, SubtitleLanguage.ENGLISH)
    workflow_id = conversation_store.get(user_id).workflow_id
    result = SubtitleResult(42, "WEB-DL", "srt", False, 1, 8.0, "uploader")
    assert conversation_store.set_subtitle_results(user_id, workflow_id, [result])

    delivery = AsyncMock()
    monkeypatch.setattr(subtitle_handler, "deliver_subtitle", delivery)

    async def run_callbacks() -> tuple[object, object]:
        message = AsyncMock(spec=Message)
        message.answer = AsyncMock()
        message.edit_reply_markup = AsyncMock()
        first = SimpleNamespace(
            from_user=User(user_id),
            data=f"subtitle:{workflow_id}:42",
            answer=AsyncMock(),
            message=message,
        )
        second = SimpleNamespace(
            from_user=User(user_id),
            data=f"subtitle:{workflow_id}:42",
            answer=AsyncMock(),
            message=message,
        )
        await asyncio.gather(
            subtitle_selected(first),  # type: ignore[arg-type]
            subtitle_selected(second),  # type: ignore[arg-type]
        )
        return first, second

    first, second = asyncio.run(run_callbacks())

    delivery.assert_awaited_once()
    first.answer.assert_awaited_once()  # type: ignore[attr-defined]
    second.answer.assert_awaited_once()  # type: ignore[attr-defined]
    answers = [
        first.answer.await_args.args,  # type: ignore[attr-defined]
        second.answer.await_args.args,  # type: ignore[attr-defined]
    ]
    assert any(args and "expired" in args[0] for args in answers)
