"""Interface onboarding and settings, driven only by explicit user actions."""

from aiogram import F, Router
from aiogram.filters import Command, Filter
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
FIRST_INTERFACE_PROMPT = (
    "زبان رابط را انتخاب کنید یا نامش را بنویسید.\n"
    "Choose your interface language or type its name:\n"
    "فارسی · English · Deutsch · Русский"
)


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
    if (
        len(parts) != 3
        or parts[2] not in {code.value for code in InterfaceLanguage}
        or not isinstance(callback.message, Message)
    ):
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


class InterfaceSearchFilter(Filter):
    async def __call__(self, message: Message, services: ApplicationServices) -> bool:
        if not message.from_user or not message.text or message.text.startswith("/"):
            return False
        keys = ("home_search", "home_language", "home_settings", "home_help", "home_about")
        if message.text in {ui(key, locale) for key in keys for locale in InterfaceLanguage}:
            return False
        return await services.interface_preferences.is_picker_open(message.from_user.id)


@router.message(InterfaceSearchFilter())
async def interface_search(message: Message, services: ApplicationServices) -> None:
    assert message.from_user is not None and message.text is not None
    try:
        outcome, matches = await services.interface_preferences.filter_picker(
            message.from_user.id, message.text
        )
        assert outcome.picker_id is not None
        await render_panel(
            message,
            ui("interface_picker") if matches else ui("language_not_found"),
            interface_keyboard(outcome.picker_id, matches),
        )
    except ApplicationError as error:
        await message.answer(present_error(error))
