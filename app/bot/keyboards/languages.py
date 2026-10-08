"""Subtitle language keyboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def language_keyboard(workflow_id: str | None = None) -> InlineKeyboardMarkup:
    prefix = f"language:{workflow_id}:" if workflow_id else "language:"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English", callback_data=f"{prefix}en")],
            [InlineKeyboardButton(text="فارسی", callback_data=f"{prefix}fa")],
        ]
    )
