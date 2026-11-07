"""Explicit interface choices; these callbacks never select subtitle languages."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.languages import InterfaceLanguage


def interface_keyboard(
    picker_id: str, matches: tuple[InterfaceLanguage, ...] | None = None
) -> InlineKeyboardMarkup:
    labels = {"fa": "فارسی 🇮🇷", "en": "English 🇬🇧", "de": "Deutsch 🇩🇪", "ru": "Русский 🇷🇺"}
    codes = matches if matches is not None else tuple(InterfaceLanguage)
    choices = [
        InlineKeyboardButton(text=labels[code], callback_data=f"interface:{picker_id}:{code}")
        for code in codes
    ]
    # Preserve the Persian/English first row used by existing clients.
    if matches is None:
        choices[0], choices[1] = choices[1], choices[0]
    return InlineKeyboardMarkup(
        inline_keyboard=[choices[i : i + 2] for i in range(0, len(choices), 2)]
    )
