"""Shared presentation for cached workflow states and recoverable UI errors."""

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.application.container import ApplicationServices
from app.application.dto import NavigationOutcome, WorkflowStage
from app.bot.keyboards.common import flow_controls
from app.bot.presentation import answer_callback, render_panel
from app.bot.presenters.errors import present_error, retryable
from app.bot.presenters.navigation import send_navigation
from app.bot.presenters.subtitles import send_subtitle_page
from app.bot.texts import ui
from app.domain.errors import ApplicationError, WorkflowExpiredError
from app.domain.models import WorkflowId


async def show_workflow(
    message: Message,
    services: ApplicationServices,
    user_id: int,
    outcome: NavigationOutcome,
    *,
    error: str | None = None,
    retry_data: str | None = None,
) -> None:
    if outcome.stage is WorkflowStage.CHOOSING_SUBTITLE:
        page = await services.deliver_subtitle.current_page(user_id, outcome.workflow_id)
        await send_subtitle_page(
            message,
            page,
            title="this title",
            language=page.language,
            edit=True,
            error=error,
            retry_data=retry_data,
        )
    elif outcome.stage in {WorkflowStage.IDLE, WorkflowStage.AWAITING_TITLE}:
        await render_panel(
            message,
            ui("title"),
            InlineKeyboardMarkup(inline_keyboard=flow_controls(outcome.workflow_id)),
            edit=True,
        )
    else:
        await send_navigation(message, outcome, edit=True, error=error, retry_data=retry_data)


async def recover_workflow(
    callback: CallbackQuery,
    services: ApplicationServices,
    workflow_id: WorkflowId,
    error: ApplicationError,
) -> None:
    if isinstance(error, WorkflowExpiredError):
        await answer_callback(callback, ui("stale"))
        return
    if not isinstance(callback.message, Message):
        return
    try:
        outcome = await services.navigate_series.current_navigation(
            callback.from_user.id, workflow_id, recover=True
        )
    except ApplicationError:
        await answer_callback(callback, ui("stale"))
        return
    retry_data = None
    parts = (callback.data or "").split(":")
    if (
        retryable(error)
        and len(parts) >= 3
        and parts[0] in {"title", "season", "episode", "language"}
    ):
        parts[1] = str(outcome.workflow_id)
        retry_data = ":".join(parts)
    await show_workflow(
        callback.message,
        services,
        callback.from_user.id,
        outcome,
        error=present_error(error),
        retry_data=retry_data,
    )
