"""Subtitle preference selection, independent of the interface language."""

import structlog
from aiogram import F, Router
from aiogram.filters import Command, Filter
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
from app.domain.languages import InterfaceLanguage, LanguageCode
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
    matches: tuple[LanguageCode, ...] | None = None,
) -> None:
    await render_panel(
        message,
        ui("picker") if matches != () else ui("language_not_found"),
        language_keyboard(workflow_id, stage=stage, matches=matches),
        edit=edit,
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
        or parts[-1] not in {code.value for code in LanguageCode}
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


class LanguageSearchFilter(Filter):
    async def __call__(self, message: Message, services: ApplicationServices) -> bool:
        if not message.from_user or not message.text or message.text.startswith("/"):
            return False
        menu_keys = ("home_search", "home_language", "home_settings", "home_help", "home_about")
        if message.text in {ui(key, locale) for key in menu_keys for locale in InterfaceLanguage}:
            return False
        return await services.choose_language.is_picker_open(message.from_user.id)


@router.message(LanguageSearchFilter())
async def language_search(message: Message, services: ApplicationServices) -> None:
    assert message.from_user is not None and message.text is not None
    try:
        outcome, matches = await services.choose_language.filter_picker(
            message.from_user.id, message.text
        )
        await show_language_picker(
            message, str(outcome.workflow_id), stage=outcome.stage, matches=matches
        )
    except ApplicationError as error:
        await message.answer(present_error(error))


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
