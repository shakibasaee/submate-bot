"""Tests for language selection and user-scoped conversation state."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.language import (
    LANGUAGE_PROMPT,
    TITLE_PROMPT,
    cancel_command,
    language_command,
    language_selected,
)
from app.bot.handlers.start import start_command
from app.bot.state import ConversationStore, SubtitleLanguage, conversation_store


class User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class MessageStub:
    def __init__(self, user_id: int = 1) -> None:
        self.from_user = User(user_id)
        self.answer = AsyncMock()


class CallbackStub:
    def __init__(self, user_id: int, data: str) -> None:
        self.from_user = User(user_id)
        self.data = data
        self.answer = AsyncMock()
        self.message = MessageStub(user_id)


@pytest.fixture(autouse=True)
def clear_conversations() -> None:
    conversation_store._conversations.clear()


def test_start_shows_the_two_language_buttons() -> None:
    message = MessageStub()

    asyncio.run(start_command(message))

    assert message.answer.await_args.args[0] == LANGUAGE_PROMPT
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert [row[0].text for row in keyboard.inline_keyboard] == ["English", "فارسی"]
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "language:en",
        "language:fa",
    ]


def test_language_command_shows_picker() -> None:
    message = MessageStub()

    asyncio.run(language_command(message))

    assert message.answer.await_args.args[0] == LANGUAGE_PROMPT


def test_selection_confirms_language_and_prompts_for_title() -> None:
    callback = CallbackStub(42, "language:fa")

    asyncio.run(language_selected(callback))

    assert callback.answer.await_args.args[0] == "Language set to فارسی."
    assert callback.message.answer.await_args.args[0] == (
        f"Language set to فارسی.\n\n{TITLE_PROMPT}"
    )
    conversation = conversation_store.get(42)
    assert conversation.language is SubtitleLanguage.PERSIAN
    assert conversation.awaiting_title is True


def test_cancel_ends_action_without_changing_language() -> None:
    conversation_store.choose_language(7, SubtitleLanguage.ENGLISH)
    conversation = conversation_store.get(7)
    conversation.selected_tmdb_id = 123
    conversation.selected_title = "Old title"
    conversation.selected_season_number = 2
    conversation.selected_episode_number = 5
    conversation.selected_subtitle_file_id = 99
    previous_workflow_id = conversation.workflow_id
    message = MessageStub(7)

    asyncio.run(cancel_command(message))

    conversation = conversation_store.get(7)
    assert conversation.language is SubtitleLanguage.ENGLISH
    assert conversation.workflow_id > previous_workflow_id
    assert conversation.awaiting_title is False
    assert conversation.selected_tmdb_id is None
    assert conversation.selected_title is None
    assert conversation.selected_season_number is None
    assert conversation.selected_episode_number is None
    assert conversation.selected_subtitle_file_id is None
    assert "cancelled" in message.answer.await_args.args[0]


def test_conversation_store_keeps_each_user_separate() -> None:
    store = ConversationStore()
    store.choose_language(1, SubtitleLanguage.ENGLISH)
    store.choose_language(2, SubtitleLanguage.PERSIAN)

    assert store.get(1).language is SubtitleLanguage.ENGLISH
    assert store.get(2).language is SubtitleLanguage.PERSIAN
