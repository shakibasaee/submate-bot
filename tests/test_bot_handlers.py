"""Public Telegram command adapters remain compatible after dependency injection."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import Message

from app.bot.handlers.language import (
    LANGUAGE_PROMPT,
    TITLE_PROMPT,
    cancel_command,
    language_selected,
)
from app.bot.handlers.search import (
    episode_selected,
    season_selected,
    title_search,
    title_selected,
)
from app.bot.handlers.start import start_command
from app.bot.handlers.subtitle import subtitle_selected
from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MediaSearchResult, MediaType, SeasonSummary, SeriesRef
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
)
from tests.support import FakeMetadata, FakeProvider, build_test_application


class User:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class MessageStub:
    def __init__(self, user_id: int = 1, text: str | None = None) -> None:
        self.from_user = User(user_id)
        self.text = text
        self.answer = AsyncMock()


class CallbackStub:
    def __init__(self, user_id: int, data: str) -> None:
        self.from_user = User(user_id)
        self.data = data
        self.answer = AsyncMock()
        self.message = MessageStub(user_id)


def telegram_message() -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    message.answer_document = AsyncMock()
    message.edit_reply_markup = AsyncMock()
    return message


def test_start_language_search_and_cancel_commands_use_application_services() -> None:
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("1", MediaType.MOVIE, "Inception", "2010")]
    )
    app = build_test_application(metadata=metadata)

    async def scenario() -> None:
        start = MessageStub(1)
        await start_command(start, app.services)  # type: ignore[arg-type]
        assert start.answer.await_args.args[0] == LANGUAGE_PROMPT

        language = CallbackStub(1, "language:en")
        await language_selected(language, app.services)  # type: ignore[arg-type]
        assert TITLE_PROMPT in language.message.answer.await_args.args[0]

        search = MessageStub(1, "Inception")
        await title_search(search, app.services)  # type: ignore[arg-type]
        assert search.answer.await_args.args[0] == "Which title did you mean?"
        keyboard = search.answer.await_args.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].callback_data.startswith("title:")

        cancel = MessageStub(1)
        await cancel_command(cancel, app.services)  # type: ignore[arg-type]
        assert "cancelled" in cancel.answer.await_args.args[0]

    asyncio.run(scenario())


def test_movie_callbacks_reach_buffered_telegram_delivery() -> None:
    candidate = SubtitleCandidate(
        ProviderId("fake"),
        ProviderFileRef("opaque"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB-DL",
        attribution="Fake provider",
    )
    provider = FakeProvider(
        candidates=[candidate],
        downloaded=DownloadedSubtitle(
            b"1\n00:00:01,000 --> 00:00:02,000\nHi\n",
            "provider.srt",
            "srt",
            "Fake provider",
        ),
    )
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
    )
    app = build_test_application(metadata=metadata, provider=provider)

    async def scenario() -> None:
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(1, "Movie")
        message = telegram_message()
        title_callback = SimpleNamespace(
            from_user=User(1),
            data=f"title:{search.workflow_id}:movie:1",
            answer=AsyncMock(),
            message=message,
        )
        await title_selected(title_callback, app.services)  # type: ignore[arg-type]
        subtitle_markup = message.answer.await_args_list[-1].kwargs["reply_markup"]
        subtitle_data = subtitle_markup.inline_keyboard[0][0].callback_data
        delivery_callback = SimpleNamespace(
            from_user=User(1),
            data=subtitle_data,
            answer=AsyncMock(),
            message=message,
        )
        await subtitle_selected(delivery_callback, app.services)  # type: ignore[arg-type]
        message.answer_document.assert_awaited_once()

    asyncio.run(scenario())


def test_tv_callbacks_navigate_season_episode_and_show_subtitles() -> None:
    series = SeriesRef("2", "Series", "2020")
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("2", MediaType.TV, "Series", "2020")],
        season_results=[SeasonSummary(2, "Season 2")],
        episode_results=[EpisodeRef("203", series, 2, 3, "Episode <Three>")],
    )
    provider = FakeProvider(
        candidates=[
            SubtitleCandidate(
                ProviderId("fake"),
                ProviderFileRef("episode"),
                LanguageCode.PERSIAN,
                "srt",
                "WEB-DL",
            )
        ]
    )
    app = build_test_application(metadata=metadata, provider=provider)

    async def scenario() -> None:
        await app.services.choose_language.execute(2, LanguageCode.PERSIAN)
        search = await app.services.search_titles.execute(2, "Series")
        message = telegram_message()
        title_callback = SimpleNamespace(
            from_user=User(2),
            data=f"title:{search.workflow_id}:tv:2",
            answer=AsyncMock(),
            message=message,
        )
        await title_selected(title_callback, app.services)  # type: ignore[arg-type]
        season_markup = message.answer.await_args.kwargs["reply_markup"]
        season_callback = SimpleNamespace(
            from_user=User(2),
            data=season_markup.inline_keyboard[0][0].callback_data,
            answer=AsyncMock(),
            message=message,
        )
        await season_selected(season_callback, app.services)  # type: ignore[arg-type]
        episode_markup = message.answer.await_args.kwargs["reply_markup"]
        episode_callback = SimpleNamespace(
            from_user=User(2),
            data=episode_markup.inline_keyboard[0][0].callback_data,
            answer=AsyncMock(),
            message=message,
        )
        await episode_selected(episode_callback, app.services)  # type: ignore[arg-type]
        assert "Episode &lt;Three&gt;" in message.answer.await_args_list[-2].args[0]
        assert "reply_markup" in message.answer.await_args_list[-1].kwargs

    asyncio.run(scenario())
