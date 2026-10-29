"""Atomic download claims and updates to one Telegram selection panel."""

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramServerError
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from app.application.container import ApplicationServices
from app.bot.handlers.language import show_language_picker
from app.bot.keyboards.common import flow_controls
from app.bot.keyboards.subtitles import recovery_keyboard, subtitle_keyboard, subtitle_label
from app.bot.presentation import answer_callback, render_panel, safe_caption
from app.bot.presenters.errors import present_error, retryable
from app.bot.presenters.subtitles import send_subtitle_page
from app.bot.texts import ui
from app.core.monitoring import monitoring
from app.domain.errors import ApplicationError, UnsafeSubtitleError, WorkflowExpiredError
from app.domain.models import WorkflowId
from app.domain.subtitles import ProviderId

router = Router(name=__name__)
logger = structlog.get_logger(__name__)


async def download_error(
    callback: CallbackQuery,
    services: ApplicationServices,
    message: Message,
    workflow: WorkflowId,
    provider: str,
    index: str,
    error: ApplicationError,
) -> None:
    if isinstance(error, WorkflowExpiredError):
        await answer_callback(callback, ui("stale"))
        return
    try:
        page = await services.deliver_subtitle.recovery_page(callback.from_user.id, workflow)
    except ApplicationError:
        await answer_callback(callback, ui("stale"))
        return
    retry = f"subtitle:{page.workflow_id}:{provider}:{index}" if retryable(error) else None
    await render_panel(
        message,
        present_error(error),
        recovery_keyboard(page, retry, invalid=isinstance(error, UnsafeSubtitleError)),
        edit=True,
    )


@router.callback_query(F.data.startswith("receipt:"))
async def receipt_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        page = await services.deliver_subtitle.acknowledge(
            callback.from_user.id, WorkflowId((callback.data or "").split(":", 1)[1])
        )
        await answer_callback(callback)
        await render_panel(
            callback.message,
            ui("receipt_resolved"),
            recovery_keyboard(page, success=True),
            edit=True,
        )
    except ApplicationError:
        await answer_callback(callback, ui("stale"))


@router.callback_query(F.data.startswith("uncertain_search:"))
async def uncertain_search_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        result = await services.start_search.execute(
            callback.from_user.id, WorkflowId((callback.data or "").split(":", 1)[1])
        )
        await answer_callback(callback)
        assert result.workflow_id is not None
        await render_panel(
            callback.message,
            ui("title"),
            InlineKeyboardMarkup(inline_keyboard=flow_controls(result.workflow_id)),
            edit=True,
        )
    except ApplicationError:
        await answer_callback(callback, ui("stale"))


@router.callback_query(F.data.startswith("subtitle:") | F.data.startswith("resend:"))
async def subtitle_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        await answer_callback(callback)
        return
    parts = callback.data.split(":", 3)
    if len(parts) != 4:
        await answer_callback(callback, ui("stale"))
        return
    workflow, provider, action = WorkflowId(parts[1]), parts[2], parts[3]
    message = callback.message
    if provider == "action" and action in {"another", "language", "search", "cancel"}:
        try:
            page = await services.deliver_subtitle.current_page(
                callback.from_user.id, workflow, rotate=True
            )
            await answer_callback(callback)
            if action == "another":
                await send_subtitle_page(
                    message, page, title="this title", language=page.language, edit=True
                )
            elif action == "language":
                await show_language_picker(message, str(page.workflow_id), edit=True)
            else:
                result = await services.start_search.execute(
                    callback.from_user.id, page.workflow_id
                )
                assert result.workflow_id is not None
                await render_panel(
                    message,
                    ui("title"),
                    InlineKeyboardMarkup(inline_keyboard=flow_controls(result.workflow_id)),
                    edit=True,
                )
        except ApplicationError:
            await answer_callback(callback, ui("stale"))
        return
    if (provider, action) == ("page", "more"):
        try:
            page = await services.find_subtitles.next_page(callback.from_user.id, workflow)
            await answer_callback(callback)
            await send_subtitle_page(
                message, page, title="this title", language=page.language, edit=True
            )
        except ApplicationError:
            await answer_callback(callback, ui("stale"))
        return
    if not action.isdigit() or provider in {"page", "action"}:
        await answer_callback(callback, ui("stale"))
        return
    try:
        attempt = await services.deliver_subtitle.claim(
            callback.from_user.id,
            workflow,
            ProviderId(provider),
            int(action),
            confirm_resend=parts[0] == "resend",
        )
    except ApplicationError as error:
        await download_error(callback, services, message, workflow, provider, action, error)
        return
    workflow = attempt.workflow_id
    await answer_callback(callback)
    try:
        try:
            panel = await render_panel(message, ui("processing"), edit=True)
            if isinstance(panel, Message):
                message = panel
        except TelegramAPIError:
            pass  # UI status failure must not discard a valid claimed download.
        outcome = await services.deliver_subtitle.download(attempt)
    except ApplicationError as error:
        await download_error(callback, services, message, workflow, provider, action, error)
        return
    except BaseException:
        await services.deliver_subtitle.restore(callback.from_user.id, workflow)
        raise
    subtitle = outcome.subtitle
    uploader = f"\n{ui('uploader')}: {subtitle.uploader}" if subtitle.uploader else ""
    try:
        await message.answer_document(
            BufferedInputFile(subtitle.content, filename=subtitle.filename),
            caption=safe_caption(f"{subtitle.attribution}{uploader}"),
        )
    except (TelegramAPIError, TimeoutError) as error:
        uncertain = isinstance(error, (TelegramNetworkError, TelegramServerError, TimeoutError))
        await services.deliver_subtitle.restore(
            callback.from_user.id,
            workflow,
            uncertain=(ProviderId(provider), int(action)) if uncertain else None,
        )
        try:
            page = await services.deliver_subtitle.recovery_page(callback.from_user.id, workflow)
            await render_panel(
                message,
                ui("upload") if uncertain else ui("upload_failed"),
                recovery_keyboard(page, f"subtitle:{page.workflow_id}:{provider}:{action}"),
                edit=True,
            )
        except ApplicationError:
            pass
        return
    except BaseException:
        await services.deliver_subtitle.restore(
            callback.from_user.id, workflow, uncertain=(ProviderId(provider), int(action))
        )
        raise
    next_id = await services.deliver_subtitle.finish(callback.from_user.id, workflow)
    monitoring.increment("deliveries", "telegram")
    logger.info("subtitle_delivered")
    try:
        page = await services.deliver_subtitle.current_page(callback.from_user.id, next_id)
        await render_panel(message, ui("sent"), recovery_keyboard(page, success=True), edit=True)
    except ApplicationError:
        pass  # A newer explicit search has already replaced this workflow.


__all__ = ["subtitle_keyboard", "subtitle_label", "subtitle_selected"]
