"""Regression coverage for uncertain receipt, decoding, privacy and local recovery."""

import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendDocument

from app.application.dto import WorkflowStage
from app.bot.handlers.home import home_action
from app.bot.handlers.privacy import privacy_command
from app.bot.handlers.subtitle import receipt_selected, subtitle_selected, uncertain_search_selected
from app.bot.localization import interface_locale
from app.bot.texts import ui
from app.core.config import Settings
from app.domain.errors import (
    MalformedSubtitleError,
    SubtitleDecodingError,
    UnsafeSubtitleContentError,
    UnsupportedSubtitleError,
    WorkflowExpiredError,
)
from app.domain.languages import InterfaceLanguage, LanguageCode
from app.infrastructure.providers.opensubtitles import validate_srt
from tests.test_button_interface import application, buttons, click, data_for, message, prepare


@pytest.mark.parametrize("resolve", ["received", "resend", "search"])
def test_uncertain_delivery_requires_an_explicit_decision_and_old_clicks_cannot_deliver(resolve):
    async def scenario():
        app = application()
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        panel = message()
        panel.answer_document.side_effect = TelegramNetworkError(
            method=SendDocument(chat_id=1, document="fixture"), message="connection lost"
        )
        old = click(f"subtitle:{initial.workflow_id}:fake:0", panel)
        await subtitle_selected(old, app.services)
        current = await app.conversations.get(1)
        assert current.stage is WorkflowStage.CONFIRMING_DELIVERY
        assert current.selected_media == initial.selected_media
        assert current.subtitle_candidates == initial.subtitle_candidates
        assert {b.text for b in buttons(panel)} == {
            ui("received"),
            ui("resend_confirm"),
            ui("search"),
        }
        assert panel.answer_document.await_count == 1
        await subtitle_selected(old, app.services)
        await subtitle_selected(
            click(f"subtitle:{current.workflow_id}:fake:0", panel), app.services
        )
        assert panel.answer_document.await_count == 1
        with pytest.raises(WorkflowExpiredError):
            await app.services.choose_language.open_picker(1, current.workflow_id)
        if resolve == "received":
            action = click(data_for(panel, "received"), panel)
            await receipt_selected(action, app.services)
            await receipt_selected(action, app.services)
            assert (await app.conversations.get(1)).stage is WorkflowStage.CHOOSING_SUBTITLE
            assert panel.answer_document.await_count == 1
        elif resolve == "search":
            action = click(data_for(panel, "search"), panel)
            await uncertain_search_selected(action, app.services)
            assert (await app.conversations.get(1)).stage is WorkflowStage.AWAITING_TITLE
            assert panel.answer_document.await_count == 1
        else:
            action = click(data_for(panel, "resend_confirm"), panel)
            panel.answer_document.side_effect = None
            await asyncio.gather(
                subtitle_selected(action, app.services), subtitle_selected(action, app.services)
            )
            assert panel.answer_document.await_count == 2
            assert (await app.conversations.get(1)).stage is WorkflowStage.CHOOSING_SUBTITLE
            assert app.provider.download_calls == 2

    asyncio.run(scenario())


def test_definite_telegram_rejection_keeps_retry_without_claiming_uncertain_receipt():
    async def scenario():
        app = application()
        current = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        panel = message()
        panel.answer_document.side_effect = TelegramBadRequest(
            method=SendDocument(chat_id=1, document="fixture"), message="upload rejected"
        )
        await subtitle_selected(
            click(f"subtitle:{current.workflow_id}:fake:0", panel), app.services
        )
        assert panel.edit_text.await_args.args[0] == ui("upload_failed")
        assert data_for(panel, "retry")
        assert (await app.conversations.get(1)).pending_delivery is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (b"1\n00:00:01,000 --> 00:00:02,000\nHello\x00\n", UnsafeSubtitleContentError),
        (
            b"1\n00:00:01,000 --> 00:00:02,000\n<script>alert(1)</script>\n",
            UnsafeSubtitleContentError,
        ),
        (b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n", UnsupportedSubtitleError),
        (b"PK\x03\x04archive", UnsupportedSubtitleError),
        (b"\xff\xfe\x01", SubtitleDecodingError),
        (b"\xef\xbb\xbf\xff", SubtitleDecodingError),
        (b"1\n00:00:02,000 --> 00:00:01,000\nHello\n", MalformedSubtitleError),
    ],
)
def test_invalid_subtitles_have_distinct_permanent_failure_categories(content, error):
    with pytest.raises(error):
        validate_srt(content, LanguageCode.ENGLISH)


def test_unicode_and_explicit_legacy_subtitle_decoding_preserve_text():
    text = "1\n00:00:01,000 --> 00:00:02,000\nسلام\n"
    for encoding in ("utf-8-sig", "utf-16", "cp1256"):
        assert validate_srt(text.encode(encoding), LanguageCode.PERSIAN).decode("utf-8") == text
    with pytest.raises(SubtitleDecodingError):
        validate_srt(text.encode("cp1256"))  # No unknown-language legacy guessing.


@pytest.mark.parametrize("locale", list(InterfaceLanguage))
def test_privacy_and_home_settings_follow_interface_without_changing_subtitle_language(locale):
    async def scenario():
        app = application()
        await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        await app.preferences.set_interface_language(1, locale)
        panel = message()
        with interface_locale(locale):
            await privacy_command(panel)
            assert panel.answer.await_args.args[0] == ui("privacy_notice")
            panel.text = ui("home_settings")
            await home_action(panel, app.services)
            assert panel.answer.await_args.args[0] == ui("interface_picker")
        assert await app.preferences.get_language(1) is LanguageCode.ENGLISH

    asyncio.run(scenario())


def test_third_party_exception_logging_redacts_urls_and_chat_identifiers():
    from app.core.logging import redact_sensitive

    event = redact_sensitive(object(), "info", {"chat": {"id": 987654321}, "update_id": 87654321})
    assert "987654321" not in str(event) and "87654321" not in str(event)
    program = """
import logging
from app.core.logging import configure_logging
configure_logging("WARNING")
private_url = "https://dl.subdl.com/subtitle/fixture?api_key=fixture-private-key"
try:
    raise RuntimeError(private_url + " chat_id=-987654321")
except RuntimeError:
    logging.getLogger("foreign").exception("Update id=87654321 failed")
"""
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    assert "fixture-private-key" not in result.stdout
    assert "987654321" not in result.stdout and "87654321" not in result.stdout
    assert "dl.subdl.com" not in result.stdout
    assert "RuntimeError" in json.loads(result.stdout)["exception"]


@pytest.mark.parametrize("failure", ["cancel", "health_start", "health_close", "router"])
def test_main_releases_resources_after_cancellation_and_partial_failure(monkeypatch, failure):
    from app import main

    bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()), me=AsyncMock())
    runtime = SimpleNamespace(close=AsyncMock(), health=AsyncMock(), services=object())
    health = SimpleNamespace(start=AsyncMock(), close=AsyncMock())
    dispatcher = SimpleNamespace(
        include_router=Mock(),
        resolve_used_update_types=Mock(return_value=[]),
        start_polling=AsyncMock(),
    )
    if failure == "cancel":
        dispatcher.start_polling.side_effect = asyncio.CancelledError
    elif failure == "health_start":
        health.start.side_effect = RuntimeError("health startup failed")
    elif failure == "health_close":
        health.close.side_effect = RuntimeError("health cleanup failed")
        runtime.close.side_effect = RuntimeError("runtime cleanup also failed")
    else:
        dispatcher.include_router.side_effect = RuntimeError("router failed")
    monkeypatch.setattr(main, "configure_logging", lambda _: None)
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz"),
    )
    monkeypatch.setattr(main, "Bot", lambda **_: bot)
    monkeypatch.setattr(main, "Dispatcher", lambda: dispatcher)
    monkeypatch.setattr(main, "build_router", lambda: object())
    monkeypatch.setattr(main, "build_runtime", AsyncMock(return_value=runtime))
    monkeypatch.setattr(main, "HealthServer", lambda *_: health)
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else RuntimeError):
        asyncio.run(main.run())
    bot.session.close.assert_awaited_once()
    if failure != "router":
        runtime.close.assert_awaited_once()
        health.close.assert_awaited_once()


def test_local_launcher_probes_the_same_token_lock_without_stopping_any_process(
    monkeypatch, tmp_path
):
    from app.core.polling_lock import polling_lock
    from scripts import local_bot

    monkeypatch.setattr(local_bot, "polling_lock", lambda token: polling_lock(token, tmp_path))
    assert not local_bot.is_running("fixture-token")
    with polling_lock("fixture-token", tmp_path):
        assert local_bot.is_running("fixture-token")
        assert not local_bot.is_running("different-fixture-token")


def test_startup_reconnects_after_an_exhausted_network_batch(monkeypatch):
    from aiogram.methods import GetMe

    from app import main

    failure = TelegramNetworkError(method=GetMe(), message="network unavailable")
    bot = SimpleNamespace(me=AsyncMock(side_effect=[failure, failure, failure, object()]))
    sleep = AsyncMock()
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    asyncio.run(main.wait_for_telegram(bot))
    assert bot.me.await_count == 4
    assert any(call.args == (15,) for call in sleep.await_args_list)


def test_startup_does_not_retry_invalid_telegram_credentials(monkeypatch):
    from aiogram.exceptions import TelegramUnauthorizedError
    from aiogram.methods import GetMe

    from app import main

    bot = SimpleNamespace(
        me=AsyncMock(
            side_effect=TelegramUnauthorizedError(method=GetMe(), message="invalid credentials")
        )
    )
    sleep = AsyncMock()
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    with pytest.raises(TelegramUnauthorizedError):
        asyncio.run(main.wait_for_telegram(bot))
    assert bot.me.await_count == 1
    sleep.assert_not_awaited()
