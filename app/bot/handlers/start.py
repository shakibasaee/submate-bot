"""Welcome only after an explicit Start action or /start message."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.application.container import ApplicationServices
from app.bot.handlers.interface import show_interface_picker
from app.bot.keyboards.home import home_keyboard
from app.bot.localization import interface_locale
from app.bot.presenters.errors import present_error
from app.bot.presenters.welcome import welcome_text
from app.bot.texts import ui
from app.domain.errors import ApplicationError
from app.domain.languages import InterfaceLanguage

router = Router(name=__name__)


@router.message(CommandStart())
async def start_command(
    message: Message, services: ApplicationServices, demo_mode: bool = False
) -> None:
    if message.from_user is None:
        return
    try:
        language = await services.interface_preferences.get(message.from_user.id)
        with interface_locale(language or InterfaceLanguage.PERSIAN):
            outcome = await services.start_search.execute(message.from_user.id)
            if language is None:
                await show_interface_picker(message, services, message.from_user.id)
                return
            await message.answer(
                welcome_text(
                    getattr(message.from_user, "first_name", None),
                    outcome.language,
                    demo_mode=demo_mode,
                ),
                reply_markup=home_keyboard(),
            )
    except (ApplicationError, OSError) as error:
        await message.answer(
            present_error(error) if isinstance(error, ApplicationError) else ui("preference_error")
        )
