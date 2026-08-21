"""Render normalized subtitle pages without provider-specific knowledge."""

from aiogram.types import Message

from app.application.dto import SubtitlePageOutcome
from app.bot.keyboards.subtitles import subtitle_keyboard
from app.bot.presentation import safe_html_text
from app.domain.languages import LanguageCode


async def send_subtitle_page(
    message: Message,
    page: SubtitlePageOutcome,
    *,
    title: str,
    language: LanguageCode,
    heading: str | None = None,
) -> None:
    if not page.candidates:
        await message.answer(
            "No subtitles found. Try /language, search a different title, or try again later."
        )
        return
    language_label = "English" if language is LanguageCode.ENGLISH else "Persian"
    text = heading or (
        f"Choose a subtitle version for {safe_html_text(title, 500)}, {language_label}:"
    )
    await message.answer(text, reply_markup=subtitle_keyboard(page))
