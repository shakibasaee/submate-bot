"""Title recovery and complete, bounded season ZIP delivery."""

import asyncio
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendDocument

from app.application.dto import WorkflowStage
from app.application.use_cases.download_season import DownloadSeason, SeasonPackUnavailable
from app.bot.handlers.search import navigation_action, season_pack_selected
from app.bot.keyboards.media import seasons_keyboard
from app.bot.localization import interface_locale
from app.bot.texts import ui
from app.domain.languages import InterfaceLanguage, LanguageCode
from app.domain.models import EpisodeRef, MediaSearchResult, MediaType, SeasonSummary, SeriesRef
from app.infrastructure.cache.memory import InMemoryRateLimiter
from app.infrastructure.providers.subdl import SubdlProvider
from tests.support import FakeMetadata, build_test_application
from tests.test_button_interface import buttons, click, message
from tests.test_free_providers import payload
from tests.test_opensubtitles import VALID_SRT, FakeResponse, FakeSession

SERIES = SeriesRef("1396", "Breaking Bad", "2008")
LANGUAGE = LanguageCode.ENGLISH


class PrefixMetadata(FakeMetadata):
    async def search(self, query: str) -> list[MediaSearchResult]:
        self.queries.append(query)
        if query in {"the termi", "The Terminal List"}:
            return [
                MediaSearchResult("7", MediaType.TV, "The Terminal List", "2022"),
                MediaSearchResult("8", MediaType.MOVIE, "Terminator", "1984"),
            ]
        return []


def test_title_miss_checks_one_prefix_and_returns_only_close_provider_titles():
    async def scenario():
        metadata = PrefixMetadata()
        app = build_test_application(metadata=metadata)
        await app.services.choose_language.execute(1, LANGUAGE)
        result = await app.services.search_titles.execute(1, "the termilal list")
        assert metadata.queries == ["the termilal list", "the termi"]
        assert result.suggested
        assert [item.title for item in result.results] == ["The Terminal List"]
        assert (await app.conversations.get(1)).search_results == result.results
        result = await app.services.search_titles.execute(1, "The Terminal List")
        assert not result.suggested and len(metadata.queries) == 3

    asyncio.run(scenario())


def season_payload(*, complete=True, wrong_language=False, duplicate_url=False):
    data = payload(url="/subtitle/pack/raw1")
    pack = data["subtitles"][0]
    pack["full_season"] = True
    if complete:
        pack["unpack_files"].append(
            {
                **pack["unpack_files"][0],
                "episode": 2,
                "language": "FA" if wrong_language else "EN",
                "url": "/subtitle/pack/raw1" if duplicate_url else "/subtitle/pack/raw2",
            }
        )
    return data


@pytest.mark.parametrize(
    "overrides",
    [
        {"complete": False},
        {"wrong_language": True},
        {"duplicate_url": True},
    ],
)
def test_provider_does_not_treat_partial_or_mismatched_sets_as_a_full_pack(overrides):
    session = FakeSession(gets=[FakeResponse(payload=season_payload(**overrides))])
    provider = SubdlProvider(session, "fixture")
    assert not asyncio.run(provider.search_season(SERIES, 1, LANGUAGE, frozenset({1, 2})))
    assert len(session.requests) == 1
    assert session.requests[0].kwargs["params"]["full_season"] == "1"


async def setup_pack(*, complete=True):
    app = build_test_application()
    initial = (await app.conversations.get(1)).evolve(
        stage=WorkflowStage.CHOOSING_EPISODE,
        language=LANGUAGE,
        selected_media=SERIES,
        episodes=(EpisodeRef("1", SERIES, 1, 1, "Pilot"), EpisodeRef("2", SERIES, 1, 2, "Second")),
    )
    await app.conversations.save(initial)
    session = FakeSession(
        gets=[
            FakeResponse(payload=season_payload(complete=complete)),
            FakeResponse(body=VALID_SRT),
            FakeResponse(body=VALID_SRT),
        ]
    )
    service = DownloadSeason(
        app.conversations,
        SubdlProvider(session, "fixture"),
        InMemoryRateLimiter(),
        app.locks,
        20,
    )
    return app, service, initial, session


@pytest.mark.parametrize("uncertain", [False, True])
def test_pack_delivers_once_and_preserves_episode_navigation(uncertain):
    async def scenario():
        app, service, initial, session = await setup_pack()
        services = replace(app.services, download_season=service)
        panel = message()
        if uncertain:
            panel.answer_document.side_effect = TelegramNetworkError(
                method=SendDocument(chat_id=1, document="fixture"),
                message="timed out",
            )
        action = f"pack:{initial.workflow_id}"
        await asyncio.gather(
            season_pack_selected(click(action, panel), services),
            season_pack_selected(click(action, panel), services),
        )
        panel.answer_document.assert_awaited_once()
        upload = panel.answer_document.await_args.args[0]
        with ZipFile(BytesIO(upload.data)) as archive:
            assert archive.namelist() == ["S01E01-en.srt", "S01E02-en.srt"]
            assert all(archive.read(name) == VALID_SRT for name in archive.namelist())
        assert len(session.requests) == 3
        current = await app.conversations.get(1)
        assert current.episodes == initial.episodes
        assert current.stage is WorkflowStage.CHOOSING_EPISODE
        assert current.workflow_id != initial.workflow_id
        if uncertain:
            assert not any(b.text == ui("season_pack") for b in buttons(panel))
            panel.answer.assert_not_awaited()
        else:
            assert panel.edit_text.await_args.args[0] == ui("season_pack_sent")
            assert panel.edit_text.await_args.kwargs["reply_markup"] is None
            markup = panel.answer.await_args.kwargs["reply_markup"]
            actions = {b.text: b.callback_data for row in markup.inline_keyboard for b in row}
            assert set(actions) == {
                ui("season_pack_back_episodes"),
                ui("back_seasons"),
                ui("language"),
                ui("search"),
            }
            back = actions[ui("season_pack_back_episodes")]
            await navigation_action(click(back, panel), services)
            assert any(b.text == ui("season_pack") for b in buttons(panel))
            assert (await app.conversations.get(1)).episodes == initial.episodes
            assert len(session.requests) == 3

    asyncio.run(scenario())


@pytest.mark.parametrize("locale", list(InterfaceLanguage))
def test_generic_season_names_are_shown_once_and_real_names_are_kept(locale):
    seasons = [
        SeasonSummary(1, "  Season 01  "),
        SeasonSummary(2, "فصل ۲"),
        SeasonSummary(3, "The Final Chapter"),
    ]
    with interface_locale(locale):
        markup = seasons_keyboard(seasons, "fixture")
        labels = [b.text for row in markup.inline_keyboard[:2] for b in row]
        season = ui("season")
    assert labels == [f"{season} 1", f"{season} 2", f"{season} 3 · The Final Chapter"]
    assert markup.inline_keyboard[0][0].callback_data == "season:fixture:1"


def test_incomplete_pack_does_not_download_or_upload_any_files():
    async def scenario():
        _, service, initial, session = await setup_pack(complete=False)
        state = await service.claim(1, initial.workflow_id)
        with pytest.raises(SeasonPackUnavailable):
            await service.build(state)
        await service.finish(state)
        assert len(session.requests) == 1

    asyncio.run(scenario())
