"""Subtitle language keyboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English", callback_data="language:en")],
            [InlineKeyboardButton(text="فارسی", callback_data="language:fa")],
        ]
    )
