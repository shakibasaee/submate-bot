"""Recovery tests exercise real application state and Telegram actions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers.subtitle import subtitle_selected
from app.domain.errors import ProviderUnavailableError, WorkflowExpiredError
from app.domain.languages import LanguageCode
from app.domain.models import MediaSearchResult, MediaType
from app.domain.subtitles import DownloadedSubtitle, ProviderFileRef, ProviderId, SubtitleCandidate
from tests.support import FakeMetadata, FakeProvider, build_test_application
from tests.test_bot_handlers import User, telegram_message


def test_failure_retry_success_and_new_search():
    candidate = SubtitleCandidate(
        ProviderId("fake"), ProviderFileRef("1"), LanguageCode.ENGLISH, "srt", "WEB-DL"
    )
    provider = FakeProvider(candidates=[candidate])
    provider.download = AsyncMock(
        side_effect=[
            ProviderUnavailableError("offline"),
            DownloadedSubtitle(b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", "x.srt", "srt", "Fake"),
        ]
    )
    app = build_test_application(
        metadata=FakeMetadata(
            search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
        ),
        provider=provider,
    )

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(1, "Movie")
        await app.services.select_title.execute(1, search.workflow_id, MediaType.MOVIE, "1")
        message = telegram_message()
        callback = SimpleNamespace(
            from_user=User(1),
            data=f"subtitle:{search.workflow_id}:fake:0",
            answer=AsyncMock(),
            message=message,
        )
        await subtitle_selected(callback, app.services)
        current = await app.conversations.get(1)
        assert current.subtitle_candidates == (candidate,)
        assert current.selected_media.title == "Movie"
        assert (
            message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].text == "Retry"
        )
        await subtitle_selected(callback, app.services)
        message.answer_document.assert_awaited_once()
        await subtitle_selected(callback, app.services)
        message.answer_document.assert_awaited_once()
        current = await app.conversations.get(1)
        callback.data = f"subtitle:{current.workflow_id}:action:another"
        await subtitle_selected(callback, app.services)
        assert message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        callback.data = f"subtitle:{current.workflow_id}:action:search"
        await subtitle_selected(callback, app.services)
        second = await app.services.search_titles.execute(1, "Movie")
        assert second.workflow_id != search.workflow_id
        with pytest.raises(WorkflowExpiredError):
            await app.services.deliver_subtitle.execute(
                1, search.workflow_id, ProviderId("fake"), 0
            )

    asyncio.run(scenario())


def test_duplicate_click_during_download_is_rejected():
    candidate = SubtitleCandidate(
        ProviderId("fake"), ProviderFileRef("1"), LanguageCode.ENGLISH, "srt", "WEB-DL"
    )
    app = build_test_application(
        metadata=FakeMetadata(
            search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
        ),
        provider=FakeProvider(candidates=[candidate]),
    )

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def download(candidate):
            entered.set()
            await release.wait()
            return DownloadedSubtitle(b"valid", "x.srt", "srt", "Fake")

        app.provider.download = download
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(1, "Movie")
        await app.services.select_title.execute(1, search.workflow_id, MediaType.MOVIE, "1")
        task = asyncio.create_task(
            app.services.deliver_subtitle.execute(1, search.workflow_id, ProviderId("fake"), 0)
        )
        await entered.wait()
        with pytest.raises(WorkflowExpiredError):
            await app.services.deliver_subtitle.execute(
                1, search.workflow_id, ProviderId("fake"), 0
            )
        release.set()
        await task

    asyncio.run(scenario())


def test_contextual_language_preserves_title_and_rejects_stale_picker():
    from app.bot.handlers.language import language_selected

    candidate = SubtitleCandidate(
        ProviderId("fake"), ProviderFileRef("1"), LanguageCode.ENGLISH, "srt", "WEB-DL"
    )
    app = build_test_application(
        metadata=FakeMetadata(
            search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
        ),
        provider=FakeProvider(candidates=[candidate]),
    )

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(1, "Movie")
        await app.services.select_title.execute(1, search.workflow_id, MediaType.MOVIE, "1")
        callback = SimpleNamespace(
            from_user=User(1),
            data=f"language:{search.workflow_id}:fa",
            answer=AsyncMock(),
            message=telegram_message(),
        )
        await language_selected(callback, app.services)
        current = await app.conversations.get(1)
        assert current.selected_media.title == "Movie"
        assert current.language is LanguageCode.PERSIAN
        assert app.provider.search_queries[-1].language is LanguageCode.PERSIAN
        await language_selected(callback, app.services)
        assert (await app.conversations.get(1)).workflow_id == current.workflow_id

    asyncio.run(scenario())


def test_telegram_upload_failure_keeps_retry_available():
    from aiogram.exceptions import TelegramNetworkError
    from aiogram.methods import SendDocument

    candidate = SubtitleCandidate(
        ProviderId("fake"), ProviderFileRef("1"), LanguageCode.ENGLISH, "srt", "WEB-DL"
    )
    app = build_test_application(
        metadata=FakeMetadata(
            search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
        ),
        provider=FakeProvider(
            candidates=[candidate],
            downloaded=DownloadedSubtitle(
                b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", "x.srt", "srt", "Fake"
            ),
        ),
    )

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(1, "Movie")
        await app.services.select_title.execute(1, search.workflow_id, MediaType.MOVIE, "1")
        message = telegram_message()
        message.answer_document.side_effect = TelegramNetworkError(
            method=SendDocument(chat_id=1, document="test"), message="offline"
        )
        callback = SimpleNamespace(
            from_user=User(1),
            data=f"subtitle:{search.workflow_id}:fake:0",
            answer=AsyncMock(),
            message=message,
        )
        await subtitle_selected(callback, app.services)
        assert (await app.conversations.get(1)).subtitle_candidates == (candidate,)
        assert (
            message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].text == "Retry"
        )
        message.answer_document.side_effect = None
        await subtitle_selected(callback, app.services)
        assert message.answer_document.await_count == 2

    asyncio.run(scenario())
