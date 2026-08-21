"""Language-selection and cancellation Telegram adapters."""

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.application.container import ApplicationServices
from app.bot.keyboards.languages import language_keyboard
from app.core.logging import user_reference
from app.domain.languages import LanguageCode

router = Router(name=__name__)
logger = structlog.get_logger(__name__)

LANGUAGE_PROMPT = "Choose your subtitle language:"
TITLE_PROMPT = "Send the name of a movie or TV series."


async def show_language_picker(message: Message) -> None:
    await message.answer(LANGUAGE_PROMPT, reply_markup=language_keyboard())


@router.message(Command("language"))
async def language_command(message: Message) -> None:
    await show_language_picker(message)


@router.callback_query(F.data.in_({"language:en", "language:fa"}))
async def language_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    language = LanguageCode(callback.data.removeprefix("language:"))
    await services.choose_language.execute(callback.from_user.id, language)
    label = "English" if language is LanguageCode.ENGLISH else "فارسی"
    logger.info(
        "language_selected",
        user_ref=user_reference(callback.from_user.id),
        language=str(language),
    )
    await callback.answer(f"Language set to {label}.")
    if callback.message is not None:
        await callback.message.answer(f"Language set to {label}.\n\n{TITLE_PROMPT}")


@router.message(Command("cancel"))
async def cancel_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is not None:
        await services.cancel_workflow.execute(message.from_user.id)
    await message.answer("Current action cancelled. Use /language when you are ready to search.")


__all__: tuple[str, ...] = (
    "LANGUAGE_PROMPT",
    "TITLE_PROMPT",
    "cancel_command",
    "language_command",
    "language_keyboard",
    "language_selected",
    "show_language_picker",
)
