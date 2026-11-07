"""Language-name search, independent preferences, translation and migration safety."""

import asyncio
import sqlite3
from string import Formatter

import pytest

from app.bot.handlers.interface import interface_search
from app.bot.handlers.language import LanguageSearchFilter, language_search, language_selected
from app.bot.localization import interface_locale
from app.bot.texts import TEXTS, ui
from app.bot.translations_de_ru import TRANSLATIONS
from app.domain.errors import WorkflowExpiredError
from app.domain.languages import InterfaceLanguage, LanguageCode, find_languages
from app.infrastructure.persistence.sqlite import SqlitePreferenceRepository
from app.infrastructure.providers.opensubtitles import validate_srt
from tests.support import build_test_application
from tests.test_button_interface import click, message


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("فارسي", "fa"),
        ("عَرَبي", "ar"),
        ("ترکی", "tr"),
        ("turkce", "tr"),
        ("Deutsch", "de"),
        ("روسی", "ru"),
        ("Русский", "ru"),
        ("francais", "fr"),
        ("es", "es"),
    ],
)
def test_language_search_accepts_native_english_persian_and_codes(name, expected):
    assert LanguageCode(expected) in find_languages(name)


def test_all_german_russian_strings_and_format_arguments_are_present():
    assert set(TEXTS) <= set(TRANSLATIONS)

    def fields(text):
        return {field for _, field, _, _ in Formatter().parse(text) if field is not None}

    for key, (english, _) in TEXTS.items():
        for translation in TRANSLATIONS[key]:
            assert translation and fields(translation) == fields(english), key


def test_language_search_invalidates_old_buttons_and_does_not_search_titles():
    async def scenario():
        app = build_test_application()
        await app.services.choose_language.execute(1, LanguageCode.ENGLISH)
        await app.preferences.set_interface_language(1, InterfaceLanguage.PERSIAN)
        picker = await app.services.choose_language.open_picker(1)
        panel = message()
        panel.text = "عربی"
        assert await LanguageSearchFilter()(panel, app.services)
        await language_search(panel, app.services)
        rows = panel.answer.await_args.kwargs["reply_markup"].inline_keyboard
        selected = rows[0][0]
        assert selected.text == "العربية"
        assert not app.metadata.queries
        with pytest.raises(WorkflowExpiredError):
            await app.services.choose_language.execute(1, LanguageCode.PERSIAN, picker.workflow_id)
        await language_selected(click(selected.callback_data, panel), app.services)
        assert await app.preferences.get_language(1) is LanguageCode.ARABIC
        assert await app.preferences.get_interface_language(1) is InterfaceLanguage.PERSIAN
        panel.text = "a movie title"
        assert not await LanguageSearchFilter()(panel, app.services)

    asyncio.run(scenario())


def test_first_interface_search_is_explicit_and_single_use():
    async def scenario():
        app = build_test_application()
        first = await app.services.interface_preferences.open_picker(1)
        panel = message()
        panel.text = "روسی"
        await interface_search(panel, app.services)
        button = panel.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        assert button.text.startswith("Русский")
        with pytest.raises(WorkflowExpiredError):
            await app.services.interface_preferences.choose(
                1, first.picker_id, InterfaceLanguage.ENGLISH
            )
        await app.services.interface_preferences.choose(
            1, button.callback_data.split(":")[1], InterfaceLanguage.RUSSIAN
        )
        assert await app.preferences.get_interface_language(1) is InterfaceLanguage.RUSSIAN
        assert await app.preferences.get_language(1) is None

    asyncio.run(scenario())


def test_old_sqlite_interface_constraint_is_migrated_without_losing_preferences(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE interface_preferences (user_id INTEGER PRIMARY KEY, "
            "language TEXT NOT NULL CHECK(language IN ('en','fa')))"
        )
        connection.execute("INSERT INTO interface_preferences VALUES (1,'fa')")
    connection.close()

    async def scenario():
        store = SqlitePreferenceRepository(str(path))
        assert await store.get_interface_language(1) is InterfaceLanguage.PERSIAN
        await store.set_interface_language(2, InterfaceLanguage.RUSSIAN)
        await store.set_language(2, LanguageCode.TURKISH)
        reopened = SqlitePreferenceRepository(str(path))
        assert await reopened.get_interface_language(2) is InterfaceLanguage.RUSSIAN
        assert await reopened.get_language(2) is LanguageCode.TURKISH

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("code", "codec", "text"),
    [
        (LanguageCode.ARABIC, "cp1256", "مرحبا"),
        (LanguageCode.TURKISH, "cp1254", "Türkçe"),
        (LanguageCode.RUSSIAN, "cp1251", "Привет"),
    ],
)
def test_language_specific_legacy_decoding(code, codec, text):
    subtitle = "1\n00:00:01,000 --> 00:00:02,000\n" + text + "\n"
    assert validate_srt(subtitle.encode(codec), code).decode("utf-8") == subtitle


def test_persian_title_typing_variants_are_normalized():
    async def scenario():
        app = build_test_application()
        await app.services.choose_language.execute(1, LanguageCode.PERSIAN)
        await app.services.search_titles.execute(1, "كيان")
        assert app.metadata.queries[0] == "کیان"
        panel = message()
        picker = await app.services.choose_language.open_picker(1)
        with interface_locale(InterfaceLanguage.GERMAN):
            panel.text = ui("home_search")
            assert not await LanguageSearchFilter()(panel, app.services)
        await app.services.navigate_series.current_navigation(1, picker.workflow_id)
        assert not await app.services.choose_language.is_picker_open(1)

    asyncio.run(scenario())
