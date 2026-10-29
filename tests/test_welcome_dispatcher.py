"""Exercise real aiogram routing/middleware with an entirely offline Bot API session."""

import os
import subprocess
import sys
from pathlib import Path


def test_real_dispatcher_onboards_and_uses_saved_locale_on_next_update():
    # Isolate the process because the existing router factory owns module-level
    # Router instances; aiogram intentionally prohibits attaching them twice.
    script = r"""
import asyncio
from datetime import datetime, UTC
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, AnswerCallbackQuery, EditMessageReplyMarkup, GetMe
from aiogram.types import Message, Chat, User, CallbackQuery, Update, InlineKeyboardMarkup
from app.bot.router import build_router
from app.domain.languages import InterfaceLanguage, LanguageCode
from tests.support import build_test_application

human = User(id=1, is_bot=False, first_name="Alice <&>")
robot = User(id=123456, is_bot=True, first_name="SubMate", username="Sub_Mate_bot")

class OfflineSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []
        self.last = None
    async def close(self):
        pass
    async def stream_content(self, *args, **kwargs):
        raise AssertionError("No downloads are expected")
        yield b""
    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            self.sent.append(method)
            self.last = Message(message_id=100+len(self.sent), date=datetime.now(UTC),
                chat=Chat(id=1, type="private"), from_user=robot, text=method.text,
                reply_markup=(method.reply_markup
                    if isinstance(method.reply_markup, InlineKeyboardMarkup) else None))
            return self.last
        if isinstance(method, EditMessageReplyMarkup):
            return self.last
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, GetMe):
            return robot
        raise AssertionError(type(method).__name__)

async def run():
    app = build_test_application()
    await app.preferences.set_language(1, LanguageCode.PERSIAN)
    session = OfflineSession()
    bot = Bot("123456:abcdefghijklmnopqrstuvwxyz", session=session)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router())
    assert set(dispatcher.resolve_used_update_types()) == {"message", "callback_query"}
    async def incoming(number, text):
        await dispatcher.feed_update(bot, Update(update_id=number, message=Message(
            message_id=number, date=datetime.now(UTC), chat=Chat(id=1, type="private"),
            from_user=human, text=text)), services=app.services)
    try:
        await incoming(1, "/start")
        assert "Choose your interface language" in session.sent[-1].text
        choice = session.sent[-1].reply_markup.inline_keyboard[0][1].callback_data
        await dispatcher.feed_update(bot, Update(update_id=2, callback_query=CallbackQuery(
            id="interface-choice", from_user=human, chat_instance="offline",
            message=session.last, data=choice)), services=app.services)
        assert session.sent[-1].text.startswith("Hi Alice &lt;&amp;&gt; 👋")
        assert session.sent[-1].reply_markup.keyboard[0][0].text == "🔎 Subtitle search"
        assert await app.preferences.get_interface_language(1) is InterfaceLanguage.ENGLISH
        assert await app.preferences.get_language(1) is LanguageCode.PERSIAN
        await incoming(3, "/start")
        assert session.sent[-1].text.startswith("Hi Alice &lt;&amp;&gt; 👋")
        await incoming(4, "🌐 Subtitle language")
        assert session.sent[-1].text == "Choose your subtitle language:"
        assert not app.metadata.queries
        print("offline_dispatcher_passed")
    finally:
        await dispatcher.storage.close()
        await bot.session.close()
asyncio.run(run())
"""
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "offline_dispatcher_passed" in result.stdout
