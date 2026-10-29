"""Home actions are routed before free-text title search."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.application.container import ApplicationServices
from app.bot.handlers.help import about_command, help_command
from app.bot.handlers.interface import settings_command
from app.bot.handlers.language import language_command, show_language_picker
from app.bot.keyboards.home import home_keyboard
from app.bot.presenters.errors import present_error
from app.bot.texts import ui
from app.domain.errors import ApplicationError
from app.domain.languages import InterfaceLanguage

router = Router(name=__name__)
HOME_KEYS = ("home_search", "home_language", "home_settings", "home_help", "home_about")
HOME_ACTIONS = {ui(key, language) for key in HOME_KEYS for language in InterfaceLanguage}


@router.message(Command("search"))
async def search_command(message: Message, services: ApplicationServices) -> None:
    if message.from_user is None:
        return
    try:
        result = await services.start_search.execute(message.from_user.id)
        if result.language is None:
            picker = await services.choose_language.open_picker(message.from_user.id)
            await show_language_picker(message, str(picker.workflow_id), stage=picker.stage)
        else:
            await message.answer(ui("title"), reply_markup=home_keyboard())
    except ApplicationError as error:
        await message.answer(present_error(error))


@router.message(F.text.in_(HOME_ACTIONS))
async def home_action(message: Message, services: ApplicationServices) -> None:
    action = next(
        (
            key
            for key in HOME_KEYS
            if message.text in {ui(key, language) for language in InterfaceLanguage}
        ),
        None,
    )
    if action == "home_search":
        await search_command(message, services)
    elif action == "home_language":
        await language_command(message, services)
    elif action == "home_help":
        await help_command(message)
    elif action == "home_settings":
        await settings_command(message, services)
    elif action == "home_about":
        await about_command(message)
