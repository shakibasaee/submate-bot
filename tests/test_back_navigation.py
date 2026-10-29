"""Recovery navigation exercises application state and real Telegram adapters."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.dto import WorkflowStage
from app.bot.handlers.language import language_command, language_selected
from app.bot.handlers.search import navigation_action, season_selected
from app.bot.handlers.start import start_command
from app.bot.handlers.subtitle import subtitle_selected
from app.bot.texts import ui
from app.domain.errors import (
    ProviderUnavailableError,
    UnsafeSubtitleError,
    UnsafeSubtitleLinkError,
    WorkflowExpiredError,
)
from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MediaSearchResult, MediaType, SeasonSummary, SeriesRef
from app.domain.subtitles import DownloadedSubtitle, ProviderFileRef, ProviderId, SubtitleCandidate
from app.infrastructure.providers.opensubtitles import validate_srt
from tests.support import FakeMetadata, FakeProvider, build_test_application
from tests.test_bot_handlers import User, telegram_message

VALID = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def test_empty_episode_list_still_has_back_language_and_search():
    app, _, _ = setup_app()
    app.metadata.episode_results = []

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        found = await app.services.search_titles.execute(1, "Example Series")
        await app.services.select_title.execute(1, found.workflow_id, MediaType.TV, "2")
        message = telegram_message()
        await season_selected(callback(f"season:{found.workflow_id}:1", message), app.services)
        assert {ui(key) for key in ("back_seasons", "language", "search")} <= {
            b.text for b in buttons(message)
        }
        back = next(b.callback_data for b in buttons(message) if b.text == ui("back_seasons"))
        await navigation_action(callback(back, message), app.services)
        assert (await app.conversations.get(1)).stage is WorkflowStage.CHOOSING_SEASON

    asyncio.run(scenario())


def setup_app(tv=True, language=LanguageCode.ENGLISH, only_bad=False):
    series = SeriesRef("2", "Example Series", "2020")
    bad = SubtitleCandidate(ProviderId("fake"), ProviderFileRef("bad"), language, "srt", "Broken")
    good = SubtitleCandidate(
        ProviderId("fake"), ProviderFileRef("good"), language, "srt", "Working"
    )
    app = build_test_application(
        metadata=FakeMetadata(
            search_results=[
                MediaSearchResult(
                    "2",
                    MediaType.TV if tv else MediaType.MOVIE,
                    "Example Series" if tv else "Movie",
                    "2020",
                )
            ],
            season_results=[SeasonSummary(1, "First"), SeasonSummary(2, "Second")],
            episode_results=[
                EpisodeRef("11", series, 1, 1, "One"),
                EpisodeRef("12", series, 1, 2, "Two"),
                EpisodeRef("21", series, 2, 1, "Next season"),
            ],
        ),
        provider=FakeProvider(
            candidates=[bad] if only_bad else [bad, good],
            downloaded=DownloadedSubtitle(VALID, "source.srt", "srt", "Test provider"),
        ),
    )
    return app, bad, good


async def prepare(app, tv=True, language=LanguageCode.ENGLISH):
    await app.services.choose_language.execute(1, language)
    found = await app.services.search_titles.execute(1, "Example Series" if tv else "Movie")
    await app.services.select_title.execute(
        1, found.workflow_id, MediaType.TV if tv else MediaType.MOVIE, "2"
    )
    if tv:
        await app.services.navigate_series.select_season(1, found.workflow_id, 1)
        await app.services.navigate_series.select_episode(1, found.workflow_id, 1, 1)
    return await app.conversations.get(1)


def callback(data, message):
    return SimpleNamespace(from_user=User(1), data=data, message=message, answer=AsyncMock())


def buttons(message):
    return [
        button
        for row in message.answer.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]


@pytest.mark.parametrize("tv", [False, True])
@pytest.mark.parametrize("language", list(LanguageCode))
def test_back_after_temporary_failure_preserves_context_and_invalidates_old_actions(tv, language):
    app, bad, good = setup_app(tv, language)
    app.provider.download = AsyncMock(side_effect=ProviderUnavailableError("offline"))

    async def scenario():
        initial = await prepare(app, tv, language)
        message = telegram_message()
        failed = callback(f"subtitle:{initial.workflow_id}:fake:0", message)
        await subtitle_selected(failed, app.services)
        controls = buttons(message)
        retry = next(b.callback_data for b in controls if b.text == ui("retry"))
        back = next(b.callback_data for b in controls if b.text == ui("back_list"))
        assert {ui("language"), ui("search")} <= {b.text for b in controls}
        await subtitle_selected(callback(back, message), app.services)
        current = await app.conversations.get(1)
        assert current.selected_media == initial.selected_media
        assert current.language is language
        assert current.subtitle_candidates == (bad, good)
        assert len(app.provider.search_queries) == len(app.metadata.queries) == 1
        assert any(b.callback_data.endswith(":fake:1") for b in buttons(message))
        if tv:
            assert "S01E01" in message.answer.await_args.args[0]
        assert (
            "Example Series" in message.answer.await_args.args[0]
            if tv
            else "Movie" in message.answer.await_args.args[0]
        )
        # Repeated Back, the original download, and the displaced Retry all expire.
        for data in [back, retry, failed.data]:
            await subtitle_selected(callback(data, message), app.services)
            assert await app.conversations.get(1) == current
        app.provider.download.assert_awaited_once()
        message.answer_document.assert_not_awaited()

    asyncio.run(scenario())


def test_initial_language_picker_is_scoped_and_legacy_buttons_cannot_reset_active_search():
    app, _, _ = setup_app(tv=False)

    async def scenario():
        message = telegram_message()
        message.from_user = User(1)
        await start_command(message, app.services)
        await language_command(message, app.services)
        original = buttons(message)[1].callback_data
        await language_selected(callback(original, message), app.services)
        found = await app.services.search_titles.execute(1, "Movie")
        await app.services.select_title.execute(1, found.workflow_id, MediaType.MOVIE, "2")
        current = await app.conversations.get(1)
        for stale in [original, "language:fa"]:
            await language_selected(callback(stale, message), app.services)
            assert await app.conversations.get(1) == current
        assert await app.preferences.get_language(1) is LanguageCode.ENGLISH

    asyncio.run(scenario())


def test_concurrent_back_clicks_only_apply_one_transition():
    app, _, _ = setup_app()

    async def scenario():
        initial = await prepare(app)
        results = await asyncio.gather(
            app.services.navigate_series.back_to_episodes(1, initial.workflow_id),
            app.services.navigate_series.back_to_episodes(1, initial.workflow_id),
            return_exceptions=True,
        )
        assert sum(isinstance(result, WorkflowExpiredError) for result in results) == 1
        current = await app.conversations.get(1)
        assert current.stage is WorkflowStage.CHOOSING_EPISODE
        assert current.language is initial.language
        results = await asyncio.gather(
            app.services.navigate_series.back_to_seasons(1, current.workflow_id),
            app.services.navigate_series.back_to_seasons(1, current.workflow_id),
            return_exceptions=True,
        )
        assert sum(isinstance(result, WorkflowExpiredError) for result in results) == 1
        assert (await app.conversations.get(1)).stage is WorkflowStage.CHOOSING_SEASON
        assert len(app.provider.search_queries) == 1

    asyncio.run(scenario())


def test_pagination_and_returned_list_expire_old_candidate_indices():

    app, _, _ = setup_app(tv=False)
    app.provider.candidates = [
        SubtitleCandidate(
            ProviderId("fake"),
            ProviderFileRef(str(index)),
            LanguageCode.ENGLISH,
            "srt",
            f"Version {index}",
        )
        for index in range(7)
    ]

    async def scenario():
        initial = await prepare(app, tv=False)
        page = await app.services.find_subtitles.next_page(1, initial.workflow_id)
        assert page.offset == 5 and len(page.candidates) == 2
        with pytest.raises(WorkflowExpiredError):
            await app.services.find_subtitles.next_page(1, initial.workflow_id)
        with pytest.raises(WorkflowExpiredError):
            await app.services.deliver_subtitle.execute(
                1, initial.workflow_id, ProviderId("fake"), 0
            )
        message = telegram_message()
        click = callback(f"subtitle:{page.workflow_id}:fake:5", message)
        await subtitle_selected(click, app.services)
        await subtitle_selected(click, app.services)
        message.answer_document.assert_awaited_once()
        assert app.provider.download_calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [UnsafeSubtitleError, UnsafeSubtitleLinkError])
def test_invalid_candidate_is_removed_and_cannot_return_via_refresh_language_or_episode(failure):
    app, bad, good = setup_app()
    app.provider.download = AsyncMock(side_effect=failure("permanently invalid"))

    async def scenario():
        initial = await prepare(app)
        message = telegram_message()
        old = f"subtitle:{initial.workflow_id}:fake:0"
        await subtitle_selected(callback(old, message), app.services)
        assert not any(b.text == ui("retry") for b in buttons(message))
        current = await app.conversations.get(1)
        assert current.subtitle_candidates == (good,)
        assert (bad.provider_id, bad.provider_file_ref) in current.rejected_subtitles
        await subtitle_selected(callback(old, message), app.services)
        app.provider.download.assert_awaited_once()
        refreshed = await app.services.find_subtitles.refresh(1, current.workflow_id)
        assert refreshed.candidates == (good,)
        lang = await app.services.choose_language.execute(
            1, LanguageCode.ENGLISH, refreshed.workflow_id
        )
        refreshed = await app.services.find_subtitles.refresh(1, lang.workflow_id)
        assert refreshed.candidates == (good,)
        episodes = await app.services.navigate_series.back_to_episodes(1, refreshed.workflow_id)
        again = await app.services.navigate_series.select_episode(1, episodes.workflow_id, 1, 1)
        assert again.subtitle_page.candidates == (good,)
        message.answer_document.assert_not_awaited()

    asyncio.run(scenario())


def test_real_srt_validation_failure_removes_last_file_and_leaves_tv_navigation():
    app, _, _ = setup_app(language=LanguageCode.PERSIAN, only_bad=True)

    async def broken(candidate):
        validate_srt(b"<html>not subtitles</html>")
        raise AssertionError("validation must reject the file")

    app.provider.download = AsyncMock(side_effect=broken)

    async def scenario():
        initial = await prepare(app, language=LanguageCode.PERSIAN)
        message = telegram_message()
        await subtitle_selected(
            callback(f"subtitle:{initial.workflow_id}:fake:0", message), app.services
        )
        controls = buttons(message)
        assert not any(b.text == ui("retry") for b in controls)
        assert not (await app.conversations.get(1)).subtitle_candidates
        assert "حذف شد" in message.answer.await_args.args[0]
        controls = buttons(message)
        assert {ui(key) for key in ("language", "search", "back_episodes")} <= {
            b.text for b in controls
        }
        episode_back = next(b.callback_data for b in controls if b.text == ui("back_episodes"))
        await navigation_action(callback(episode_back, message), app.services)
        ep = await app.conversations.get(1)
        assert ep.stage is WorkflowStage.CHOOSING_EPISODE
        assert ep.selected_media == initial.selected_media.series
        assert ep.language is LanguageCode.PERSIAN
        assert len(ep.episodes) == 2
        season_back = next(
            b.callback_data for b in buttons(message) if b.text == ui("back_seasons")
        )
        await navigation_action(callback(season_back, message), app.services)
        seasons = await app.conversations.get(1)
        assert seasons.stage is WorkflowStage.CHOOSING_SEASON
        assert isinstance(seasons.selected_media, SeriesRef)
        assert len(seasons.seasons) == 2
        # Old navigation/cancel controls must not cancel or revive another stage.
        for data in [season_back, episode_back, f"nav:{initial.workflow_id}:cancel"]:
            await navigation_action(callback(data, message), app.services)
            assert await app.conversations.get(1) == seasons
        next_season = await app.services.navigate_series.select_season(1, seasons.workflow_id, 2)
        assert next_season.episodes[0].season_number == 2
        assert (await app.conversations.get(1)).language is LanguageCode.PERSIAN
        app.provider.download.assert_awaited_once()

    asyncio.run(scenario())


def test_back_navigation_cannot_interrupt_or_duplicate_inflight_delivery():
    app, _, _ = setup_app()

    async def scenario():
        initial = await prepare(app)
        entered, release = asyncio.Event(), asyncio.Event()

        async def download(candidate):
            entered.set()
            await release.wait()
            return DownloadedSubtitle(VALID, "x.srt", "srt", "Test")

        app.provider.download = AsyncMock(side_effect=download)
        task = asyncio.create_task(
            app.services.deliver_subtitle.execute(1, initial.workflow_id, ProviderId("fake"), 1)
        )
        await entered.wait()
        for method in [
            app.services.navigate_series.back_to_episodes,
            app.services.navigate_series.back_to_seasons,
            app.services.deliver_subtitle.current_page,
            app.services.cancel_workflow.execute,
            app.services.start_search.execute,
        ]:
            with pytest.raises(WorkflowExpiredError):
                await method(1, initial.workflow_id)
        with pytest.raises(WorkflowExpiredError):
            await app.services.deliver_subtitle.execute(
                1, initial.workflow_id, ProviderId("fake"), 1
            )
        release.set()
        assert (await task).subtitle.content == VALID
        await app.services.deliver_subtitle.finish(1, initial.workflow_id)
        app.provider.download.assert_awaited_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("at_episode", [False, True])
def test_contextual_language_picker_keeps_series_navigation_and_expires_old_buttons(at_episode):
    app, _, _ = setup_app()

    async def scenario():
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        found = await app.services.search_titles.execute(1, "Example Series")
        await app.services.select_title.execute(1, found.workflow_id, MediaType.TV, "2")
        if at_episode:
            await app.services.navigate_series.select_season(1, found.workflow_id, 1)
        message = telegram_message()
        await navigation_action(
            callback(f"nav:{found.workflow_id}:language", message), app.services
        )
        current = await app.conversations.get(1)
        choice = callback(f"language:{current.workflow_id}:fa", message)
        await language_selected(choice, app.services)
        updated = await app.conversations.get(1)
        assert updated.language is LanguageCode.PERSIAN
        assert updated.stage is (
            WorkflowStage.CHOOSING_EPISODE if at_episode else WorkflowStage.CHOOSING_SEASON
        )
        assert isinstance(updated.selected_media, SeriesRef)
        assert any(
            b.callback_data.startswith("episode:" if at_episode else "season:")
            for b in buttons(message)
        )
        await language_selected(choice, app.services)
        assert await app.conversations.get(1) == updated
        assert not app.provider.search_queries

    asyncio.run(scenario())
