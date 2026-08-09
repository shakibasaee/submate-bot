"""Language-selection and cancellation handlers."""

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.state import SubtitleLanguage, conversation_store
from app.core.infrastructure import infrastructure
from app.core.logging import user_reference

router = Router(name=__name__)
logger = structlog.get_logger(__name__)

LANGUAGE_PROMPT = "Choose your subtitle language:"
TITLE_PROMPT = "Send the name of a movie or TV series."


def language_keyboard() -> InlineKeyboardMarkup:
    """Create the language picker used by /start and /language."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English", callback_data="language:en")],
            [InlineKeyboardButton(text="فارسی", callback_data="language:fa")],
        ]
    )


async def show_language_picker(message: Message) -> None:
    """Ask a user to choose the language for their next subtitle search."""
    await message.answer(LANGUAGE_PROMPT, reply_markup=language_keyboard())


@router.message(Command("language"))
async def language_command(message: Message) -> None:
    """Let a user change the subtitle language at any time."""
    await show_language_picker(message)


@router.callback_query(F.data.in_({"language:en", "language:fa"}))
async def language_selected(callback: CallbackQuery) -> None:
    """Persist a language choice and prompt for a title."""
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return

    language = SubtitleLanguage(callback.data.removeprefix("language:"))
    conversation_store.choose_language(callback.from_user.id, language)
    await infrastructure.save_language(callback.from_user.id, str(language))
    logger.info(
        "language_selected",
        user_ref=user_reference(callback.from_user.id),
        language=str(language),
    )
    label = "English" if language is SubtitleLanguage.ENGLISH else "فارسی"
    await callback.answer(f"Language set to {label}.")
    if callback.message is not None:
        await callback.message.answer(f"Language set to {label}.\n\n{TITLE_PROMPT}")


@router.message(Command("cancel"))
async def cancel_command(message: Message) -> None:
    """Safely stop the current title-entry action."""
    if message.from_user is not None:
        conversation_store.cancel(message.from_user.id)
    await message.answer("Current action cancelled. Use /language when you are ready to search.")
