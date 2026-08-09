"""Help command."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name=__name__)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    """Explain the currently available commands."""
    await message.answer(
        "Commands:\n"
        "/start — choose a subtitle language\n"
        "/language — change the selected subtitle language\n"
        "/cancel — end the current action\n"
        "/privacy — show privacy, copyright, and provider information\n"
        "/help — show this help"
    )
