"""Language-selection and cancellation Telegram adapters."""

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.application.container import ApplicationServices
from app.bot.keyboards.languages import language_keyboard
from app.bot.presentation import remove_inline_keyboard
from app.bot.presenters.errors import present_error
from app.bot.presenters.subtitles import send_subtitle_page
from app.core.logging import user_reference
from app.domain.errors import ApplicationError
from app.domain.languages import LanguageCode
from app.domain.models import WorkflowId

router = Router(name=__name__)
logger = structlog.get_logger(__name__)

LANGUAGE_PROMPT = "Choose your subtitle language:"
TITLE_PROMPT = "Send the name of a movie or TV series."


async def show_language_picker(message: Message, workflow_id: str | None = None) -> None:
    await message.answer(LANGUAGE_PROMPT, reply_markup=language_keyboard(workflow_id))


@router.message(Command("language"))
async def language_command(message: Message) -> None:
    await show_language_picker(message)


@router.callback_query(F.data.startswith("language:"))
async def language_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) not in {2, 3} or parts[-1] not in {"en", "fa"}:
        await callback.answer("Invalid language selection.")
        return
    language = LanguageCode(parts[-1])
    try:
        outcome = await services.choose_language.execute(
            callback.from_user.id, language, WorkflowId(parts[1]) if len(parts) == 3 else None
        )
        if len(parts) == 3:
            await callback.answer("Language updated.")
            if isinstance(callback.message, Message):
                await remove_inline_keyboard(callback.message)
                page = await services.find_subtitles.refresh(
                    callback.from_user.id, outcome.workflow_id
                )
                await send_subtitle_page(
                    callback.message, page, title="this title", language=language
                )
            return
    except ApplicationError as error:
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(present_error(error))
        return
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
