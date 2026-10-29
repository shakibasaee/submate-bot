"""UI contracts: persistent menu, cached pages, one panel, and atomic delivery."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import EditMessageText, SendDocument
from aiogram.types import Message

from app.application.dto import WorkflowStage
from app.bot.handlers.home import home_action
from app.bot.handlers.language import language_selected
from app.bot.handlers.search import (
    episode_selected,
    navigation_action,
    page_selected,
    title_selected,
)
from app.bot.handlers.start import start_command
from app.bot.handlers.subtitle import subtitle_selected
from app.bot.keyboards.home import home_keyboard
from app.bot.keyboards.subtitles import subtitle_label
from app.bot.presentation import render_panel
from app.bot.router import build_router
from app.bot.texts import ui
from app.domain.errors import (
    ProviderUnavailableError,
    UnsafeSubtitleError,
    WorkflowExpiredError,
)
from app.domain.languages import InterfaceLanguage, LanguageCode
from app.domain.models import EpisodeRef, MediaSearchResult, MediaType, SeasonSummary, SeriesRef
from app.domain.subtitles import DownloadedSubtitle, ProviderFileRef, ProviderId, SubtitleCandidate
from tests.support import FakeMetadata, FakeProvider, build_test_application
from tests.test_bot_handlers import User

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def message():
    result = AsyncMock(spec=Message)
    result.from_user = User(1)
    result.text = None
    result.answer = AsyncMock()
    result.edit_text = AsyncMock()
    result.answer_document = AsyncMock()
    return result


def click(data, panel):
    return SimpleNamespace(from_user=User(1), data=data, message=panel, answer=AsyncMock())


def buttons(panel):
    return [
        b for row in panel.edit_text.await_args.kwargs["reply_markup"].inline_keyboard for b in row
    ]


def data_for(panel, label):
    return next(b.callback_data for b in buttons(panel) if b.text == ui(label))


def application():
    series = SeriesRef("200", "Example Series", "2020")
    provider = FakeProvider(
        candidates=[
            SubtitleCandidate(
                ProviderId("fake"),
                ProviderFileRef(f"{i:02}"),
                LanguageCode.ENGLISH,
                "srt",
                f"Release {i:02}",
            )
            for i in range(12)
        ],
        downloaded=DownloadedSubtitle(SRT, "source.srt", "srt", "Test provider"),
    )
    return build_test_application(
        metadata=FakeMetadata(
            search_results=[
                MediaSearchResult(str(i), MediaType.MOVIE, f"Movie {i}", "2020")
                for i in range(1, 22)
            ]
            + [MediaSearchResult("200", MediaType.TV, series.title, series.year)],
            season_results=[SeasonSummary(i, f"Season name {i}") for i in range(1, 61)],
            episode_results=[
                EpisodeRef(str(i), series, 1, i, f"Episode name {i}") for i in range(1, 66)
            ],
        ),
        provider=provider,
    )


async def prepare(app, stage):
    await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
    found = await app.services.search_titles.execute(1, "Example")
    if stage is not WorkflowStage.CHOOSING_TITLE:
        await app.services.select_title.execute(
            1,
            found.workflow_id,
            MediaType.TV if stage is not WorkflowStage.CHOOSING_SUBTITLE else MediaType.MOVIE,
            "200" if stage is not WorkflowStage.CHOOSING_SUBTITLE else "1",
        )
    if stage is WorkflowStage.CHOOSING_EPISODE:
        await app.services.navigate_series.select_season(1, found.workflow_id, 1)
    return await app.conversations.get(1)


def test_permanent_home_menu_and_router_priority():
    keyboard = home_keyboard()
    assert keyboard.is_persistent and keyboard.resize_keyboard
    assert [[b.text for b in row] for row in keyboard.keyboard] == [
        ["🔎 جست‌وجوی زیرنویس", "🌐 زبان زیرنویس"],
        ["⚙️ تنظیمات", "❓ راهنما"],
    ]
    routers = [r.name for r in build_router().sub_routers]
    assert routers.index("app.bot.handlers.home") < routers.index("app.bot.handlers.search")


def test_start_reports_saved_subtitle_language_and_home_actions_do_not_search_their_labels():
    app = application()

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        await app.preferences.set_interface_language(1, InterfaceLanguage.PERSIAN)
        panel = message()
        await start_command(panel, app.services)
        assert "English" in panel.answer.await_args.args[0]
        assert "SubMate" in panel.answer.await_args.args[0]
        assert panel.answer.await_args.kwargs["reply_markup"].is_persistent
        initial = await app.conversations.get(1)
        for key in ("home_help", "home_about"):
            panel.text = ui(key)
            await home_action(panel, app.services)
            assert await app.conversations.get(1) == initial
        panel.text = ui("home_language")
        await home_action(panel, app.services)
        assert panel.answer.await_args.args[0] == ui("picker")
        assert not app.metadata.queries
        assert not app.provider.search_queries
        panel.text = ui("home_search")
        await home_action(panel, app.services)
        assert panel.answer.await_args.args[0] == ui("title")
        assert not app.metadata.queries

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "kind,stage",
    [
        ("t", WorkflowStage.CHOOSING_TITLE),
        ("s", WorkflowStage.CHOOSING_SEASON),
        ("e", WorkflowStage.CHOOSING_EPISODE),
        ("u", WorkflowStage.CHOOSING_SUBTITLE),
    ],
)
def test_every_list_pages_both_ways_in_the_same_panel_and_rejects_stale_pages(kind, stage):
    app = application()

    async def scenario():
        initial = await prepare(app, stage)
        panel = message()
        original = f"page:{initial.workflow_id}:{kind}:1"
        before = len(app.metadata.queries), len(app.provider.search_queries)
        await page_selected(click(original, panel), app.services)
        updated = await app.conversations.get(1)
        assert updated.workflow_id != initial.workflow_id
        assert data_for(panel, "previous").endswith(":0")
        assert any(b.text.startswith("2 / ") for b in buttons(panel))
        panel.answer.assert_not_awaited()
        edits = panel.edit_text.await_count
        stale = click(original, panel)
        await page_selected(stale, app.services)
        assert panel.edit_text.await_count == edits
        assert stale.answer.await_args.args[0] == ui("stale")
        assert await app.conversations.get(1) == updated
        await page_selected(click(data_for(panel, "previous"), panel), app.services)
        assert any(b.text.startswith("1 / ") for b in buttons(panel))
        assert not any(b.text == ui("previous") for b in buttons(panel))
        assert (len(app.metadata.queries), len(app.provider.search_queries)) == before
        assert all(len(b.callback_data.encode()) <= 64 for b in buttons(panel))

    asyncio.run(scenario())


def test_episode_after_fifty_is_reachable_and_back_keeps_the_correct_list_pages():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_EPISODE)
        panel = message()
        await page_selected(click(f"page:{initial.workflow_id}:e:8", panel), app.services)
        assert any(b.callback_data.endswith(":1:65") for b in buttons(panel))
        assert any(b.text == "9 / 9" for b in buttons(panel))
        assert any("Episode name 65" in b.text for b in buttons(panel))
        current = await app.conversations.get(1)
        await app.services.navigate_series.select_episode(1, current.workflow_id, 1, 65)
        await navigation_action(click(f"nav:{current.workflow_id}:episodes", panel), app.services)
        assert any(b.callback_data.endswith(":1:65") for b in buttons(panel))
        assert any(b.text == "9 / 9" for b in buttons(panel))
        assert (await app.conversations.get(1)).selected_media == initial.selected_media

    asyncio.run(scenario())


def test_movie_and_season_can_return_to_cached_title_results_without_new_search():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_TITLE)
        second = await app.services.navigate_series.page_at(
            1, initial.workflow_id, WorkflowStage.CHOOSING_TITLE, 8
        )
        panel = message()
        await title_selected(click(f"title:{second.workflow_id}:movie:9", panel), app.services)
        assert data_for(panel, "back_titles")
        await navigation_action(click(data_for(panel, "back_titles"), panel), app.services)
        assert any(b.text == "2 / 3" for b in buttons(panel))
        current = await app.conversations.get(1)
        await title_selected(click(f"title:{current.workflow_id}:tv:200", panel), app.services)
        assert data_for(panel, "back_titles")
        await navigation_action(click(data_for(panel, "back_titles"), panel), app.services)
        assert len(app.metadata.queries) == 1
        assert (await app.conversations.get(1)).language is LanguageCode.ENGLISH
        panel.answer.assert_not_awaited()

    asyncio.run(scenario())


def test_subtitle_language_changes_do_not_change_interface_and_picker_has_back():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        panel = message()
        await navigation_action(click(f"nav:{initial.workflow_id}:language", panel), app.services)
        assert panel.edit_text.await_args.args[0] == ui("picker")
        assert data_for(panel, "back")
        picker = await app.conversations.get(1)
        await language_selected(click(f"language:{picker.workflow_id}:fa", panel), app.services)
        assert "زبان زیرنویس: فارسی" in panel.edit_text.await_args.args[0]
        assert {ui("language"), ui("search"), ui("back_titles")} <= {b.text for b in buttons(panel)}
        assert app.provider.search_queries[-1].language is LanguageCode.PERSIAN
        assert (await app.conversations.get(1)).selected_media == initial.selected_media
        panel.answer.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("tv", [False, True])
def test_success_has_only_contextual_actions_and_duplicate_delivery_does_not_edit_the_panel(tv):
    app = application()

    async def scenario():
        initial = await prepare(
            app, WorkflowStage.CHOOSING_EPISODE if tv else WorkflowStage.CHOOSING_SUBTITLE
        )
        if tv:
            await app.services.navigate_series.select_episode(1, initial.workflow_id, 1, 1)
        panel = message()
        original = f"subtitle:{initial.workflow_id}:fake:0"
        await subtitle_selected(click(original, panel), app.services)
        assert panel.edit_text.await_args_list[0].args[0] == ui("processing")
        assert panel.edit_text.await_args_list[0].kwargs["reply_markup"] is None
        rows = panel.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        assert [b.text for b in rows[0]] == [ui("another"), ui("language")]
        assert rows[-1][0].text == ui("search")
        assert any(b.text == ui("other_episode") for b in buttons(panel)) is tv
        assert not any(b.text in {ui("retry"), ui("back_titles")} for b in buttons(panel))
        edits = panel.edit_text.await_count
        await subtitle_selected(click(original, panel), app.services)
        assert panel.edit_text.await_count == edits
        panel.answer_document.assert_awaited_once()
        panel.answer.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("unsafe", [False, True])
def test_errors_replace_processing_with_real_recovery_actions_and_no_status_spam(unsafe):
    app = application()
    failure = UnsafeSubtitleError("invalid SRT") if unsafe else ProviderUnavailableError("offline")
    app.provider.download = AsyncMock(side_effect=failure)

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        panel = message()
        await subtitle_selected(
            click(f"subtitle:{initial.workflow_id}:fake:0", panel), app.services
        )
        assert panel.edit_text.await_count == 2
        assert any(b.text == ui("retry") for b in buttons(panel)) is (not unsafe)
        assert data_for(panel, "another" if unsafe else "back_list")
        state = await app.conversations.get(1)
        assert len(state.subtitle_candidates) == (11 if unsafe else 12)
        panel.answer.assert_not_awaited()
        panel.answer_document.assert_not_awaited()

    asyncio.run(scenario())


def test_busy_claim_blocks_download_and_menu_duplicates_while_progress_is_visible():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        entered, release = asyncio.Event(), asyncio.Event()

        async def download(candidate):
            entered.set()
            await release.wait()
            return DownloadedSubtitle(SRT, "x.srt", "srt", "Test")

        app.provider.download = AsyncMock(side_effect=download)
        panel = message()
        data = f"subtitle:{initial.workflow_id}:fake:0"
        task = asyncio.create_task(subtitle_selected(click(data, panel), app.services))
        await entered.wait()
        await subtitle_selected(click(data, panel), app.services)
        assert panel.edit_text.await_count == 1
        assert (await app.conversations.get(1)).stage is WorkflowStage.DELIVERING
        home = message()
        home.text = ui("home_search")
        await home_action(home, app.services)
        assert (await app.conversations.get(1)).stage is WorkflowStage.DELIVERING
        assert home.answer.await_args.args[0] == ui("busy")
        release.set()
        await task
        app.provider.download.assert_awaited_once()
        panel.answer_document.assert_awaited_once()

    asyncio.run(scenario())


def test_cancelled_progress_restores_choices_before_provider_download():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        entered = asyncio.Event()

        async def edit(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        panel = message()
        panel.edit_text.side_effect = edit
        task = asyncio.create_task(
            subtitle_selected(click(f"subtitle:{initial.workflow_id}:fake:0", panel), app.services)
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        current = await app.conversations.get(1)
        assert current.stage is WorkflowStage.CHOOSING_SUBTITLE
        assert current.subtitle_candidates == initial.subtitle_candidates
        assert not current.download_started
        assert app.provider.download_calls == 0

    asyncio.run(scenario())


def test_a_claim_cannot_start_the_same_provider_download_twice():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        attempt = await app.services.deliver_subtitle.claim(
            1, initial.workflow_id, ProviderId("fake"), 0
        )
        await app.services.deliver_subtitle.download(attempt)
        with pytest.raises(WorkflowExpiredError):
            await app.services.deliver_subtitle.download(attempt)
        assert app.provider.download_calls == 1

    asyncio.run(scenario())


def test_actual_metadata_only_and_long_labels_remain_bounded():
    candidate = SubtitleCandidate(
        ProviderId("fake"), ProviderFileRef("file"), LanguageCode.ENGLISH, "srt", "Release" * 30
    )
    assert "★" not in subtitle_label(candidate) and "↓" not in subtitle_label(candidate)
    real = replace(candidate, hearing_impaired=True, forced=True, rating=8.5, download_count=42)
    label = subtitle_label(real)
    assert all(tag in label for tag in ("SRT", "HI", "اجباری", "★8.5", "↓42"))
    assert len(label) <= 64


@pytest.mark.parametrize("mode", ["unchanged", "uneditable", "network"])
def test_panel_edit_fallback_distinguishes_unchanged_uneditable_and_uncertain_network(mode):
    panel = message()
    method = EditMessageText(chat_id=1, message_id=1, text="test")
    panel.edit_text.side_effect = (
        TelegramNetworkError(method=method, message="offline")
        if mode == "network"
        else TelegramBadRequest(
            method=method,
            message="message is not modified" if mode == "unchanged" else "message can't be edited",
        )
    )

    async def scenario():
        if mode == "network":
            with pytest.raises(TelegramNetworkError):
                await render_panel(panel, "text", edit=True)
        else:
            await render_panel(panel, "text", edit=True)
        assert panel.answer.await_count == (1 if mode == "uneditable" else 0)

    asyncio.run(scenario())


def test_telegram_upload_failure_keeps_same_panel_and_replaces_retry_nonce():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        panel = message()
        panel.answer_document.side_effect = TelegramNetworkError(
            method=SendDocument(chat_id=1, document="example"), message="offline"
        )
        await subtitle_selected(
            click(f"subtitle:{initial.workflow_id}:fake:0", panel), app.services
        )
        assert panel.edit_text.await_args.args[0] == ui("upload")
        assert str(initial.workflow_id) not in data_for(panel, "resend_confirm")
        assert not any(b.text == ui("retry") for b in buttons(panel))
        assert data_for(panel, "received")
        panel.answer.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("where", ["title", "season", "episode"])
def test_failed_metadata_or_subtitle_lookup_retires_the_click_before_queued_duplicates(where):
    app = application()

    async def scenario():
        stage = {
            "title": WorkflowStage.CHOOSING_TITLE,
            "season": WorkflowStage.CHOOSING_SEASON,
            "episode": WorkflowStage.CHOOSING_EPISODE,
        }[where]
        initial = await prepare(app, stage)
        entered, release = asyncio.Event(), asyncio.Event()

        async def fail(*args):
            entered.set()
            await release.wait()
            raise ProviderUnavailableError("offline")

        mocked = AsyncMock(side_effect=fail)
        if where == "season":
            app.metadata.episodes = mocked
            operation = app.services.navigate_series.select_season
            args = (1, initial.workflow_id, 1)
        elif where == "title":
            app.provider.search = mocked
            operation = app.services.select_title.execute
            args = (1, initial.workflow_id, MediaType.MOVIE, "1")
        else:
            app.provider.search = mocked
            operation = app.services.navigate_series.select_episode
            args = (1, initial.workflow_id, 1, 1)
        first = asyncio.create_task(operation(*args))
        await entered.wait()
        second = asyncio.create_task(operation(*args))
        release.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert isinstance(results[0], ProviderUnavailableError)
        assert isinstance(results[1], WorkflowExpiredError)
        mocked.assert_awaited_once()
        current = await app.conversations.get(1)
        assert current.stage is stage and current.workflow_id != initial.workflow_id
        assert current.language is initial.language

    asyncio.run(scenario())


@pytest.mark.parametrize("language_change", [False, True])
def test_temporary_search_failure_has_a_working_retry_and_does_not_overwrite_newer_panels(
    language_change,
):
    app = application()

    async def scenario():
        initial = await prepare(
            app,
            WorkflowStage.CHOOSING_SUBTITLE if language_change else WorkflowStage.CHOOSING_EPISODE,
        )
        panel = message()
        original = (
            f"language:{initial.workflow_id}:fa"
            if language_change
            else f"episode:{initial.workflow_id}:1:1"
        )
        handler = language_selected if language_change else episode_selected
        app.provider.search = AsyncMock(
            side_effect=[ProviderUnavailableError("offline"), app.provider.candidates]
        )
        await handler(click(original, panel), app.services)
        retry = data_for(panel, "retry")
        assert str(initial.workflow_id) not in retry
        await handler(click(retry, panel), app.services)
        assert "نسخهٔ زیرنویس" in panel.edit_text.await_args.args[0]
        edits = panel.edit_text.await_count
        await handler(click(original, panel), app.services)
        assert panel.edit_text.await_count == edits
        assert app.provider.search.await_count == 2
        panel.answer.assert_not_awaited()

    asyncio.run(scenario())
