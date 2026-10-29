"""Show the selected media, actual subtitle language and candidate versions."""

from aiogram.types import Message

from app.application.dto import SubtitlePageOutcome
from app.bot.keyboards.common import button
from app.bot.keyboards.subtitles import subtitle_keyboard
from app.bot.presentation import render_panel, safe_html_text
from app.bot.texts import subtitle_language_label, ui
from app.domain.languages import LanguageCode


async def send_subtitle_page(
    message: Message,
    page: SubtitlePageOutcome,
    *,
    title: str,
    language: LanguageCode,
    heading: str | None = None,
    edit: bool = False,
    error: str | None = None,
    retry_data: str | None = None,
) -> None:
    title = page.title if page.is_episode or title == "this title" else title
    text = (
        f"{safe_html_text(title, 500)}\n"
        f"{ui('subtitle_language')}: {subtitle_language_label(page.language)}\n\n"
        + (ui("choose_version") if page.candidates else ui("empty"))
    )
    if error:
        text = f"{error}\n\n{text}"
    if page.pending_delivery is not None:
        text = ui("upload")
    markup = subtitle_keyboard(page)
    if retry_data and page.pending_delivery is None:
        markup.inline_keyboard.insert(0, [button("retry", retry_data)])
    await render_panel(message, text, markup, edit=edit)
