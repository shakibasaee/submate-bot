"""Basic public commands."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.handlers.language import show_language_picker
from app.bot.state import SubtitleLanguage, conversation_store
from app.core.infrastructure import infrastructure

router = Router(name=__name__)


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    """Welcome a user and open the subtitle-language picker."""
    if message.from_user is not None:
        saved_language = await infrastructure.load_language(message.from_user.id)
        if saved_language in {"en", "fa"}:
            conversation_store.restore_language(
                message.from_user.id, SubtitleLanguage(saved_language)
            )
    await show_language_picker(message)
