"""Interface onboarding and settings, driven only by explicit user actions."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.application.container import ApplicationServices
from app.bot.keyboards.home import home_keyboard
from app.bot.keyboards.interface import interface_keyboard
from app.bot.localization import current_interface_language, interface_locale
from app.bot.presentation import answer_callback, remove_inline_keyboard, render_panel
from app.bot.presenters.errors import present_error
from app.bot.presenters.welcome import welcome_text
from app.bot.texts import ui
from app.domain.errors import ApplicationError, WorkflowExpiredError
from app.domain.languages import InterfaceLanguage

router = Router(name=__name__)
FIRST_INTERFACE_PROMPT = "زبان رابط را انتخاب کنید:\nChoose your interface language:"


async def show_interface_picker(
    message: Message, services: ApplicationServices, user_id: int, *, edit: bool = False
) -> None:
    outcome = await services.interface_preferences.open_picker(user_id)
    assert outcome.picker_id is not None
    with interface_locale(outcome.language or current_interface_language()):
        prompt = FIRST_INTERFACE_PROMPT if outcome.language is None else ui("interface_picker")
        await render_panel(message, prompt, interface_keyboard(outcome.picker_id), edit=edit)


@router.message(Command("settings"))
async def settings_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is None:
        return
    try:
        await show_interface_picker(message, services, message.from_user.id)
    except ApplicationError as error:
        await message.answer(present_error(error))


@router.callback_query(F.data == "settings:open")
async def settings_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    await answer_callback(callback)
    if not isinstance(callback.message, Message):
        return
    try:
        await show_interface_picker(callback.message, services, callback.from_user.id, edit=True)
    except ApplicationError as error:
        await render_panel(callback.message, present_error(error), edit=True)


@router.callback_query(F.data.startswith("interface:"))
async def interface_selected(
    callback: CallbackQuery, services: ApplicationServices, demo_mode: bool = False
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[2] not in {"en", "fa"} or not isinstance(callback.message, Message):
        await answer_callback(callback, ui("interface_stale"))
        return
    try:
        outcome = await services.interface_preferences.choose(
            callback.from_user.id, parts[1], InterfaceLanguage(parts[2])
        )
    except ApplicationError as error:
        await answer_callback(
            callback,
            ui("interface_stale")
            if isinstance(error, WorkflowExpiredError)
            else present_error(error),
        )
        return
    assert outcome.language is not None
    with interface_locale(outcome.language):
        await answer_callback(callback)
        await remove_inline_keyboard(callback.message)
        await callback.message.answer(
            welcome_text(
                getattr(callback.from_user, "first_name", None),
                outcome.subtitle_language,
                demo_mode=demo_mode,
            ),
            reply_markup=home_keyboard(),
        )
