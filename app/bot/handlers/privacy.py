"""Privacy, copyright, and provider-attribution notice."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.texts import ui
from app.domain.languages import InterfaceLanguage

router = Router(name=__name__)

PRIVACY_NOTICE = ui("privacy_notice", InterfaceLanguage.ENGLISH)


@router.message(Command("privacy"))
async def privacy_command(message: Message) -> None:
    """Show the data-use, copyright, and provider notice."""
    await message.answer(ui("privacy_notice"))
