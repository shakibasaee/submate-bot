"""Start-command Telegram adapter."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.application.container import ApplicationServices
from app.bot.handlers.language import TITLE_PROMPT, show_language_picker

router = Router(name=__name__)


@router.message(CommandStart())
async def start_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is not None:
        outcome = await services.start_search.execute(message.from_user.id)
        if outcome.language is not None:
            await message.answer(TITLE_PROMPT)
            return
    await show_language_picker(message)
