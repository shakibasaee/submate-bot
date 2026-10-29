"""Independent interface onboarding, safe names, persistence and locale isolation."""

import asyncio
import sqlite3
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from psycopg import Error as PsycopgError

from app.application.dto import WorkflowStage
from app.application.use_cases.interface_preferences import InterfacePreferences
from app.application.use_cases.start_search import StartSearch
from app.bot.handlers.help import about_command, help_command
from app.bot.handlers.home import home_action
from app.bot.handlers.interface import interface_selected, settings_command, settings_selected
from app.bot.handlers.start import start_command
from app.bot.localization import current_interface_language, interface_locale
from app.bot.middleware import InterfaceLocaleMiddleware
from app.bot.presenters.welcome import display_name, welcome_text
from app.bot.texts import ui
from app.domain.errors import WorkflowExpiredError
from app.domain.languages import InterfaceLanguage, LanguageCode
from app.infrastructure.persistence.memory import InMemoryPreferenceRepository
from app.infrastructure.persistence.postgres import PostgresPreferenceRepository
from app.infrastructure.persistence.sqlite import SqlitePreferenceRepository
from tests.support import build_test_application
from tests.test_button_interface import application, message, prepare


def user(name="Alice <&>", user_id=1):
    return SimpleNamespace(id=user_id, first_name=name)


def callback(data, panel, sender=None):
    return SimpleNamespace(data=data, message=panel, from_user=sender or user(), answer=AsyncMock())


def interface_data(panel, code):
    return next(
        b.callback_data
        for row in panel.answer.await_args.kwargs["reply_markup"].inline_keyboard
        for b in row
        if b.callback_data.endswith(f":{code}")
    )


@pytest.mark.parametrize("interface", list(InterfaceLanguage))
@pytest.mark.parametrize("subtitle", [None, *LanguageCode])
def test_first_start_chooses_only_interface_then_personalizes_and_reuses_saved_language(
    interface, subtitle
):
    app = build_test_application()

    async def scenario():
        if subtitle is not None:
            await app.preferences.set_language(1, subtitle)
        panel = message()
        panel.from_user = user("Original name")
        panel.edit_reply_markup = AsyncMock()
        await start_command(panel, app.services)
        text = panel.answer.await_args.args[0]
        assert "زبان رابط" in text and "Choose your interface language" in text
        rows = panel.answer.await_args.kwargs["reply_markup"].inline_keyboard
        assert [b.text for b in rows[0]] == ["فارسی 🇮🇷", "English 🇬🇧"]
        assert all(len(b.callback_data.encode()) <= 64 for b in rows[0])
        assert await app.preferences.get_interface_language(1) is None
        assert await app.preferences.get_language(1) is subtitle
        original = interface_data(panel, str(interface))
        # The callback user is the human, whereas the message author is the bot.
        panel.from_user = user("Bot display name")
        selection = callback(original, panel, user("Alice <&>"))
        await interface_selected(selection, app.services)
        welcome = panel.answer.await_args.args[0]
        assert welcome.startswith(
            "Hi Alice &lt;&amp;&gt; 👋"
            if interface is InterfaceLanguage.ENGLISH
            else "سلام Alice &lt;&amp;&gt; 👋"
        )
        assert "Bot display name" not in welcome and "Original name" not in welcome
        assert (
            "Welcome to SubMate!"
            if interface is InterfaceLanguage.ENGLISH
            else "به SubMate خوش اومدی!"
        ) in welcome
        keyboard = panel.answer.await_args.kwargs["reply_markup"]
        assert keyboard.is_persistent and len(keyboard.keyboard) == 2
        assert keyboard.keyboard[0][0].text == ui("home_search", interface)
        assert await app.preferences.get_interface_language(1) is interface
        assert await app.preferences.get_language(1) is subtitle
        assert (await app.conversations.get(1)).language is subtitle
        calls = panel.answer.await_count
        await interface_selected(selection, app.services)
        assert panel.answer.await_count == calls  # A consumed picker cannot greet twice.
        assert await app.preferences.get_interface_language(1) is interface
        later = message()
        later.from_user = user("Mina")
        await start_command(later, app.services)
        assert later.answer.await_args.args[0].startswith(
            "Hi Mina" if interface is InterfaceLanguage.ENGLISH else "سلام Mina"
        )
        assert later.answer.await_args.kwargs["reply_markup"].is_persistent
        assert "Choose your interface language" not in later.answer.await_args.args[0]
        assert await app.preferences.get_language(1) is subtitle

    asyncio.run(scenario())


@pytest.mark.parametrize("name", [None, " \n\t", "\x00\u202e\u200c", "👻", {"name": "invalid"}])
def test_unusable_display_names_have_generic_welcomes(name):
    assert display_name(name) is None
    for interface in InterfaceLanguage:
        with interface_locale(interface):
            text = welcome_text(name, None)
            assert text.startswith(
                "Hi 👋\n" if interface is InterfaceLanguage.ENGLISH else "سلام 👋\n"
            )
            assert "None" not in text and "{first_name}" not in text


def test_display_name_escaping_controls_and_length_are_safe_for_html():
    name = "\u202e<b>Alice & Bob</b>\x00\nnext"
    safe = display_name(name)
    assert safe == "&lt;b&gt;Alice &amp; Bob&lt;/b&gt; next"
    assert "\u202e" not in safe and "\x00" not in safe
    with interface_locale(InterfaceLanguage.ENGLISH):
        text = welcome_text(name, LanguageCode.PERSIAN)
        assert "<b>" not in text and "&lt;b&gt;" in text
        assert "Saved subtitle language: فارسی" in text
        assert len(welcome_text("A" * 10000, None)) < 4096


def test_settings_entry_changes_interface_without_resetting_active_subtitle_choices():
    app = application()

    async def scenario():
        initial = await prepare(app, WorkflowStage.CHOOSING_SUBTITLE)
        await app.preferences.set_interface_language(1, InterfaceLanguage.PERSIAN)
        panel = message()
        panel.edit_reply_markup = AsyncMock()
        await about_command(panel)
        settings = panel.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
        assert settings.text == ui("settings")
        await settings_selected(callback(settings.callback_data, panel), app.services)
        picker = await app.conversations.get(1)
        assert picker.selected_media == initial.selected_media
        english = f"interface:{picker.interface_picker_id}:en"
        await interface_selected(callback(english, panel, user("Nina")), app.services)
        assert panel.answer.await_args.args[0].startswith("Hi Nina")
        assert await app.conversations.get(1) == initial
        assert await app.preferences.get_language(1) is LanguageCode.ENGLISH
        assert await app.preferences.get_interface_language(1) is InterfaceLanguage.ENGLISH
        # The typed settings path works too; opening a newer picker expires the old one.
        command = message()
        command.from_user = user()
        await settings_command(command, app.services)
        old = interface_data(command, "fa")
        await settings_command(command, app.services)
        fresh = interface_data(command, "fa")
        calls = command.answer.await_count
        await interface_selected(callback(old, command), app.services)
        assert command.answer.await_count == calls
        assert await app.preferences.get_interface_language(1) is InterfaceLanguage.ENGLISH
        await interface_selected(callback(fresh, command), app.services)
        assert await app.preferences.get_interface_language(1) is InterfaceLanguage.PERSIAN
        assert await app.preferences.get_language(1) is LanguageCode.ENGLISH
        assert (await app.conversations.get(1)).subtitle_candidates == initial.subtitle_candidates

    asyncio.run(scenario())


def test_interface_choice_is_serialized_for_repeated_and_competing_clicks():
    app = build_test_application()

    async def scenario():
        picker = await app.services.interface_preferences.open_picker(1)
        assert picker.picker_id
        results = await asyncio.gather(
            app.services.interface_preferences.choose(
                1, picker.picker_id, InterfaceLanguage.ENGLISH
            ),
            app.services.interface_preferences.choose(
                1, picker.picker_id, InterfaceLanguage.PERSIAN
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, WorkflowExpiredError) for result in results) == 1
        assert await app.preferences.get_interface_language(1) in set(InterfaceLanguage)
        assert await app.preferences.get_language(1) is None

    asyncio.run(scenario())


def test_sqlite_additive_schema_and_start_after_repository_replacement(tmp_path):
    path = str(tmp_path / "preferences.sqlite3")
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE preferences (user_id INTEGER PRIMARY KEY, language TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO preferences VALUES (1, 'en')")
    connection.commit()
    connection.close()

    async def scenario():
        first = SqlitePreferenceRepository(path)
        assert await first.get_interface_language(1) is None
        await first.set_interface_language(1, InterfaceLanguage.PERSIAN)
        assert await first.get_language(1) is LanguageCode.ENGLISH
        await first.set_interface_language(2, InterfaceLanguage.ENGLISH)
        assert await first.get_language(2) is None
        await first.close()
        second = SqlitePreferenceRepository(path)
        assert await second.get_interface_language(1) is InterfaceLanguage.PERSIAN
        assert await second.get_language(1) is LanguageCode.ENGLISH
        assert await second.get_interface_language(2) is InterfaceLanguage.ENGLISH
        # A newly built application uses durable UI settings immediately on /start.
        app = build_test_application()
        app.services = replace(
            app.services,
            start_search=StartSearch(app.conversations, second, app.locks),
            interface_preferences=InterfacePreferences(app.conversations, second, app.locks),
        )
        panel = message()
        panel.from_user = user("Restarted")
        await start_command(panel, app.services)
        assert panel.answer.await_args.args[0].startswith("سلام Restarted")
        assert panel.answer.await_args.kwargs["reply_markup"].is_persistent
        assert "English" in panel.answer.await_args.args[0]
        await second.set_language(1, LanguageCode.PERSIAN)
        assert (
            await SqlitePreferenceRepository(path).get_interface_language(1)
            is InterfaceLanguage.PERSIAN
        )

    asyncio.run(scenario())
    connection = sqlite3.connect(path)
    columns = connection.execute("PRAGMA table_info(interface_preferences)").fetchall()
    assert {column[1] for column in columns} == {"user_id", "language"}
    connection.close()


def test_locale_middleware_isolates_parallel_users_and_resets_after_exceptions():
    app = build_test_application()
    middleware = InterfaceLocaleMiddleware()

    async def scenario():
        await app.preferences.set_interface_language(1, InterfaceLanguage.ENGLISH)
        await app.preferences.set_interface_language(2, InterfaceLanguage.PERSIAN)
        await app.preferences.set_language(1, LanguageCode.PERSIAN)
        await app.preferences.set_language(2, LanguageCode.ENGLISH)

        async def handler(event, data):
            first = ui("welcome")
            await asyncio.sleep(0)
            return first, ui("welcome"), ui("home_search")

        english, persian = await asyncio.gather(
            middleware(
                handler, SimpleNamespace(from_user=user(user_id=1)), {"services": app.services}
            ),
            middleware(
                handler, SimpleNamespace(from_user=user(user_id=2)), {"services": app.services}
            ),
        )
        assert english[:2] == ("Welcome to SubMate!", "Welcome to SubMate!")
        assert persian[:2] == ("به SubMate خوش اومدی!", "به SubMate خوش اومدی!")
        assert english[2] == "🔎 Subtitle search" and persian[2] == "🔎 جست‌وجوی زیرنویس"
        assert current_interface_language() is InterfaceLanguage.PERSIAN

        async def fail(event, data):
            assert current_interface_language() is InterfaceLanguage.ENGLISH
            raise RuntimeError("handler failed")

        with pytest.raises(RuntimeError):
            await middleware(fail, SimpleNamespace(from_user=user()), {"services": app.services})
        assert current_interface_language() is InterfaceLanguage.PERSIAN

    asyncio.run(scenario())


def test_english_interface_routes_old_persian_home_labels_and_localizes_subtitle_picker():
    from app.bot.handlers.language import language_command

    app = build_test_application()

    async def scenario():
        await app.preferences.set_language(1, LanguageCode.PERSIAN)
        panel = message()
        with interface_locale(InterfaceLanguage.ENGLISH):
            panel.text = ui("home_search", InterfaceLanguage.PERSIAN)
            await home_action(panel, app.services)
            assert panel.answer.await_args.args[0] == "Send the name of a movie or TV series."
            await language_command(panel, app.services)
            assert panel.answer.await_args.args[0] == "Choose your subtitle language:"
            await help_command(panel)
            assert "Interface language" in panel.answer.await_args.args[0]
            await about_command(panel)
            assert (
                panel.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].text
                == "⚙️ Settings"
            )
        assert not app.metadata.queries
        assert await app.preferences.get_language(1) is LanguageCode.PERSIAN

    asyncio.run(scenario())


def test_failed_interface_save_keeps_picker_retryable_and_hides_storage_details():
    app = build_test_application()

    async def scenario():
        await app.preferences.set_language(1, LanguageCode.ENGLISH)
        panel = message()
        panel.edit_reply_markup = AsyncMock()
        panel.from_user = user()
        await start_command(panel, app.services)
        data = interface_data(panel, "fa")
        current = await app.conversations.get(1)
        app.preferences.set_interface_language = AsyncMock(
            side_effect=RuntimeError("private-storage-detail")
        )
        choice = callback(data, panel)
        sent = panel.answer.await_count
        await interface_selected(choice, app.services)
        assert panel.answer.await_count == sent
        assert choice.answer.await_args.args[0] == ui("preference_error")
        assert "private-storage-detail" not in str(choice.answer.await_args)
        assert (await app.conversations.get(1)).interface_picker_id == current.interface_picker_id
        assert await app.preferences.get_language(1) is LanguageCode.ENGLISH
        assert await app.preferences.get_interface_language(1) is None

    asyncio.run(scenario())


class FakePostgresConnection:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        if self.pool.offline:
            raise PsycopgError("offline")
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, sql, params=None):
        self.pool.statements.append(sql)
        if params and sql.lstrip().startswith("INSERT"):
            target = (
                self.pool.interface if "user_interface_preferences" in sql else self.pool.subtitle
            )
            target[params[0]] = params[1]
        if params and sql.lstrip().startswith("SELECT"):
            target = (
                self.pool.interface if "user_interface_preferences" in sql else self.pool.subtitle
            )
            value = target.get(params[0])
            return SimpleNamespace(fetchone=AsyncMock(return_value=(value,) if value else None))
        return None


class FakePostgresPool:
    def __init__(self):
        self.interface = {}
        self.subtitle = {1: "en"}
        self.statements = []
        self.offline = False

    def connection(self, timeout):
        return FakePostgresConnection(self)


def test_postgres_interface_storage_and_memory_fallback_do_not_change_subtitle_preferences():
    pool = FakePostgresPool()
    fallback = InMemoryPreferenceRepository()
    repository = PostgresPreferenceRepository(pool, fallback)

    async def scenario():
        await repository.ensure_schema()
        assert len([sql for sql in pool.statements if "CREATE TABLE" in sql]) == 2
        await repository.set_interface_language(1, InterfaceLanguage.PERSIAN)
        assert await repository.get_language(1) is LanguageCode.ENGLISH
        assert await repository.get_interface_language(1) is InterfaceLanguage.PERSIAN
        assert pool.subtitle == {1: "en"}
        pool.offline = True
        await repository.set_interface_language(1, InterfaceLanguage.ENGLISH)
        assert await repository.get_interface_language(1) is InterfaceLanguage.ENGLISH
        assert await repository.get_language(1) is LanguageCode.ENGLISH
        assert await fallback.get_language(1) is LanguageCode.ENGLISH
        assert await fallback.get_interface_language(1) is InterfaceLanguage.ENGLISH

    asyncio.run(scenario())
