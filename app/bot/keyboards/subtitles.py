"""Provider-neutral subtitle candidate keyboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.dto import SubtitlePageOutcome
from app.bot.presentation import safe_button_text
from app.domain.subtitles import SubtitleCandidate


def subtitle_label(candidate: SubtitleCandidate) -> str:
    labels = [candidate.release_name, candidate.format.upper()]
    if candidate.hearing_impaired:
        labels.append("HI")
    if candidate.forced:
        labels.append("Forced")
    if candidate.download_count is not None:
        labels.append(f"↓{candidate.download_count}")
    if candidate.rating is not None:
        labels.append(f"★{candidate.rating:g}")
    return safe_button_text(" — ".join(labels))


def subtitle_keyboard(page: SubtitlePageOutcome) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=subtitle_label(candidate),
                callback_data=(
                    f"subtitle:{page.workflow_id}:{candidate.provider_id}:{page.offset + index}"
                ),
            )
        ]
        for index, candidate in enumerate(page.candidates)
    ]
    if page.has_more:
        rows.append(
            [
                InlineKeyboardButton(
                    text="More results",
                    callback_data=f"subtitle:{page.workflow_id}:page:more",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Change language",
                callback_data=f"subtitle:{page.workflow_id}:action:language",
            ),
            InlineKeyboardButton(
                text="Cancel",
                callback_data=f"subtitle:{page.workflow_id}:action:cancel",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
