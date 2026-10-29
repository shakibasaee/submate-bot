"""Personalized HTML-safe welcome; names are never stored or logged."""

import unicodedata

from app.bot.presentation import safe_html_text, truncate_text
from app.bot.texts import subtitle_language_label, ui
from app.domain.languages import LanguageCode


def display_name(first_name: object) -> str | None:
    if not isinstance(first_name, str):
        return None
    compact = " ".join(first_name.split())
    compact = "".join(
        char
        for char in compact
        if not unicodedata.category(char).startswith("C") or char == "\u200c"
    )
    if not any(char.isalnum() for char in compact):
        return None
    return safe_html_text(truncate_text(compact.strip(), 80), 300)


def welcome_text(
    first_name: object, subtitle_language: LanguageCode | None, *, demo_mode: bool = False
) -> str:
    name = display_name(first_name)
    greeting = ui("greeting_named").format(name=name) if name else ui("greeting")
    text = (
        f"{greeting}\n{ui('welcome')}\n{ui('welcome_search')}\n\n"
        f"{ui('saved_subtitle')}: {subtitle_language_label(subtitle_language)}"
    )
    if demo_mode:
        text += f"\n\n{ui('demo_notice')}"
    return text
