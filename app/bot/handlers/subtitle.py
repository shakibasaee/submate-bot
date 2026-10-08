"""Thin Telegram adapter for subtitle pagination and delivery."""

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.application.container import ApplicationServices
from app.bot.handlers.language import TITLE_PROMPT, show_language_picker
from app.bot.keyboards.subtitles import subtitle_keyboard, subtitle_label
from app.bot.presentation import remove_inline_keyboard, safe_caption
from app.bot.presenters.errors import present_error
from app.bot.presenters.subtitles import send_subtitle_page
from app.core.logging import user_reference
from app.core.monitoring import monitoring
from app.domain.errors import ApplicationError
from app.domain.models import WorkflowId
from app.domain.subtitles import ProviderId

router = Router(name=__name__)
logger = structlog.get_logger(__name__)


@router.callback_query(F.data.startswith("subtitle:"))
async def subtitle_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 3)
    if len(parts) != 4:
        await callback.answer("That subtitle selection is invalid.", show_alert=True)
        return
    workflow_id = WorkflowId(parts[1])
    provider_id = parts[2]
    action = parts[3]
    await callback.answer("Cancelled." if (provider_id, action) == ("action", "cancel") else None)
    message = callback.message
    if not isinstance(message, Message):
        return

    if (provider_id, action) == ("action", "cancel"):
        try:
            await services.deliver_subtitle.current_page(callback.from_user.id, workflow_id)
        except ApplicationError as error:
            await message.answer(present_error(error))
            return
        await remove_inline_keyboard(message)
        await services.cancel_workflow.execute(callback.from_user.id)
        return
    if provider_id == "action" and action in {"language", "search", "another"}:
        try:
            page = await services.deliver_subtitle.current_page(callback.from_user.id, workflow_id)
        except ApplicationError as error:
            await message.answer(present_error(error))
            return
        await remove_inline_keyboard(message)
        if action == "language":
            await show_language_picker(message, str(workflow_id))
        elif action == "search":
            await services.start_search.execute(callback.from_user.id)
            await message.answer(TITLE_PROMPT)
        else:
            await send_subtitle_page(message, page, title="this title", language=page.language)
        return
    if (provider_id, action) == ("page", "more"):
        try:
            page = await services.find_subtitles.next_page(callback.from_user.id, workflow_id)
        except ApplicationError as error:
            await message.answer(present_error(error))
            return
        await remove_inline_keyboard(message)
        await send_subtitle_page(
            message,
            page,
            title="this title",
            language=page.language,
            heading="More subtitle results:",
        )
        return
    if not action.isdigit() or provider_id in {"page", "action"}:
        await message.answer("That subtitle selection is invalid.")
        return
    await remove_inline_keyboard(message)
    try:
        outcome = await services.deliver_subtitle.execute(
            callback.from_user.id,
            workflow_id,
            ProviderId(provider_id),
            int(action),
        )
    except ApplicationError as error:
        markup = None
        try:
            await services.deliver_subtitle.current_page(callback.from_user.id, workflow_id)
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Retry", callback_data=callback.data)],
                    [
                        InlineKeyboardButton(
                            text="Search another title",
                            callback_data=f"subtitle:{workflow_id}:action:search",
                        )
                    ],
                ]
            )
        except ApplicationError:
            pass
        await message.answer(present_error(error), reply_markup=markup)
        return

    subtitle = outcome.subtitle
    uploader = f"\nUploader: {subtitle.uploader}" if subtitle.uploader else ""
    document = BufferedInputFile(subtitle.content, filename=subtitle.filename)
    try:
        await message.answer_document(
            document,
            caption=safe_caption(f"{subtitle.attribution}{uploader}"),
        )
    except TelegramAPIError:
        await services.deliver_subtitle.restore(callback.from_user.id, workflow_id)
        await message.answer(
            "Telegram could not confirm file delivery. Check the chat before retrying.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Retry", callback_data=callback.data)],
                    [
                        InlineKeyboardButton(
                            text="Search another title",
                            callback_data=f"subtitle:{workflow_id}:action:search",
                        )
                    ],
                ]
            ),
        )
        return
    next_id = await services.deliver_subtitle.finish(callback.from_user.id, workflow_id)
    await message.answer(
        "Subtitle sent. What next?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Another subtitle", callback_data=f"subtitle:{next_id}:action:another"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Search another title",
                        callback_data=f"subtitle:{next_id}:action:search",
                    )
                ],
            ]
        ),
    )
    monitoring.increment("deliveries", "telegram")
    logger.info("subtitle_delivered", user_ref=user_reference(callback.from_user.id))


__all__ = ["subtitle_keyboard", "subtitle_label", "subtitle_selected"]
