"""Explicit interface choices; these callbacks never select subtitle languages."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def interface_keyboard(picker_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="فارسی 🇮🇷", callback_data=f"interface:{picker_id}:fa"),
                InlineKeyboardButton(text="English 🇬🇧", callback_data=f"interface:{picker_id}:en"),
            ]
        ]
    )
