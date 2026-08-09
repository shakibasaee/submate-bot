"""Telegram-safe rendering helpers for untrusted provider and metadata text."""

import re
from html import escape
from inspect import isawaitable
from typing import Any

from aiogram.exceptions import TelegramAPIError

TELEGRAM_BUTTON_TEXT_LIMIT = 64
TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def truncate_text(value: str, limit: int) -> str:
    """Bound text without returning a partial ellipsis beyond Telegram's limit."""
    if limit < 1:
        return ""
    if len(value) <= limit:
        return value
    if limit == 1:
        return "…"
    return f"{value[: limit - 1].rstrip()}…"


def clean_external_text(value: str) -> str:
    """Remove control characters that should never reach Telegram presentation."""
    return _CONTROL_CHARACTERS.sub("", value)


def safe_button_text(value: str) -> str:
    """Return a single-line label within Telegram's button text limit."""
    compact = " ".join(clean_external_text(value).split()) or "Untitled"
    return truncate_text(compact, TELEGRAM_BUTTON_TEXT_LIMIT)


def safe_html_text(value: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> str:
    """Escape external text before interpolation into an HTML-mode message."""
    if limit < 1:
        return ""
    rendered: list[str] = []
    rendered_length = 0
    for character in clean_external_text(value):
        escaped_character = escape(character, quote=False)
        if rendered_length + len(escaped_character) > limit:
            if rendered_length < limit:
                rendered.append("…")
            break
        rendered.append(escaped_character)
        rendered_length += len(escaped_character)
    return "".join(rendered)


def safe_caption(value: str) -> str:
    """Escape and bound a complete Telegram document caption."""
    return safe_html_text(value, TELEGRAM_CAPTION_LIMIT)


async def remove_inline_keyboard(message: Any) -> None:
    """Best-effort removal of a keyboard that has already served its purpose."""
    edit_reply_markup = getattr(message, "edit_reply_markup", None)
    if not callable(edit_reply_markup):
        return
    try:
        result = edit_reply_markup(reply_markup=None)
        if isawaitable(result):
            await result
    except TelegramAPIError:
        # Selection validity is enforced server-side even when Telegram cannot edit an old message.
        return
