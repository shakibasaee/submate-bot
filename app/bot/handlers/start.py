"""Start-command Telegram adapter."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.application.container import ApplicationServices
from app.bot.handlers.language import show_language_picker

router = Router(name=__name__)


@router.message(CommandStart())
async def start_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is not None:
        await services.start_search.execute(message.from_user.id)
    await show_language_picker(message)
