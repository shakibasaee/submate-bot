"""The persistent four-button home keyboard."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.texts import ui


def home_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ui("home_search")), KeyboardButton(text=ui("home_language"))],
            [KeyboardButton(text=ui("home_settings")), KeyboardButton(text=ui("home_help"))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=ui("search_placeholder"),
    )
