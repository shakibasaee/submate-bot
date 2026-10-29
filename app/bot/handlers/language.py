"""Subtitle preference selection, independent of the interface language."""

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.application.container import ApplicationServices
from app.application.dto import WorkflowStage
from app.bot.keyboards.home import home_keyboard
from app.bot.keyboards.languages import language_keyboard
from app.bot.presentation import answer_callback, render_panel
from app.bot.presenters.errors import present_error
from app.bot.presenters.subtitles import send_subtitle_page
from app.bot.presenters.workflow import recover_workflow, show_workflow
from app.bot.texts import ui
from app.core.logging import user_reference
from app.domain.errors import ApplicationError
from app.domain.languages import LanguageCode
from app.domain.models import WorkflowId

router = Router(name=__name__)
logger = structlog.get_logger(__name__)
LANGUAGE_PROMPT = ui("picker")
TITLE_PROMPT = ui("title")


async def show_language_picker(
    message: Message,
    workflow_id: str | None = None,
    *,
    stage: WorkflowStage = WorkflowStage.CHOOSING_SUBTITLE,
    edit: bool = False,
) -> None:
    await render_panel(
        message, ui("picker"), language_keyboard(workflow_id, stage=stage), edit=edit
    )


@router.message(Command("language"))
async def language_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is None:
        return
    try:
        outcome = await services.choose_language.open_picker(message.from_user.id)
        await show_language_picker(message, str(outcome.workflow_id), stage=outcome.stage)
    except ApplicationError as error:
        await message.answer(present_error(error))


@router.callback_query(F.data.startswith("language:"))
async def language_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    parts = (callback.data or "").split(":")
    if (
        len(parts) != 3
        or parts[-1] not in {"en", "fa"}
        or not isinstance(callback.message, Message)
    ):
        await answer_callback(callback, ui("stale"))
        return
    workflow = WorkflowId(parts[1])
    language = LanguageCode(parts[2])
    await answer_callback(callback)
    try:
        outcome = await services.choose_language.execute(callback.from_user.id, language, workflow)
        workflow = outcome.workflow_id
        logger.info(
            "language_selected",
            user_ref=user_reference(callback.from_user.id),
            language=str(language),
        )
        if outcome.stage is WorkflowStage.CHOOSING_SUBTITLE:
            page = await services.find_subtitles.refresh(callback.from_user.id, workflow)
            await send_subtitle_page(
                callback.message, page, title="this title", language=language, edit=True
            )
        else:
            nav = await services.navigate_series.current_navigation(callback.from_user.id, workflow)
            await show_workflow(callback.message, services, callback.from_user.id, nav)
    except ApplicationError as error:
        await recover_workflow(callback, services, workflow, error)


@router.message(Command("cancel"))
async def cancel_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is not None:
        await services.cancel_workflow.execute(message.from_user.id)
    await message.answer(ui("cancel_done"), reply_markup=home_keyboard())


__all__ = [
    "LANGUAGE_PROMPT",
    "TITLE_PROMPT",
    "cancel_command",
    "language_command",
    "language_keyboard",
    "language_selected",
    "show_language_picker",
]
