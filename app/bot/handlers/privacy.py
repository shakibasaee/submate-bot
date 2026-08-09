"""Privacy, copyright, and provider-attribution notice."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name=__name__)

PRIVACY_NOTICE = (
    "Privacy: the bot stores your Telegram user ID and subtitle-language preference. "
    "Search text is not stored in PostgreSQL or intentionally written to logs. TMDb and "
    "OpenSubtitles receive the identifiers and language needed to perform your request.\n\n"
    "Copyright: subtitles remain the work of their respective authors. Files are provided "
    "by OpenSubtitles.com for personal, lawful use and include provider/uploader attribution "
    "when available."
)


@router.message(Command("privacy"))
async def privacy_command(message: Message) -> None:
    """Show the data-use, copyright, and provider notice."""
    await message.answer(PRIVACY_NOTICE)
