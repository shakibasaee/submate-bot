"""Subtitle versions, real metadata and context-specific next actions."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.dto import SubtitlePageOutcome
from app.bot.keyboards.common import button, flow_controls, pagination
from app.bot.presentation import safe_button_text, truncate_text
from app.bot.texts import ui
from app.domain.subtitles import SubtitleCandidate


def subtitle_label(candidate: SubtitleCandidate) -> str:
    labels = [candidate.language.value.upper(), candidate.format.upper()]
    if candidate.hearing_impaired:
        labels.append("HI")
    if candidate.forced:
        labels.append(ui("forced"))
    if candidate.download_count is not None:
        labels.append(f"↓{candidate.download_count}")
    if candidate.rating is not None:
        labels.append(f"★{candidate.rating:g}")
    details = " · ".join(labels)
    release = truncate_text(candidate.release_name, max(12, 61 - len(details)))
    return safe_button_text(f"{release} · {details}")


def subtitle_keyboard(page: SubtitlePageOutcome) -> InlineKeyboardMarkup:
    if page.pending_delivery is not None:
        return recovery_keyboard(page)
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
    rows.extend(pagination(page.workflow_id, "u", page.total, page.offset, 5))
    rows.extend(
        flow_controls(
            page.workflow_id,
            "episodes" if page.is_episode else "titles",
            "back_episodes" if page.is_episode else "back_titles",
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recovery_keyboard(
    page: SubtitlePageOutcome,
    retry_data: str | None = None,
    *,
    success: bool = False,
    invalid: bool = False,
) -> InlineKeyboardMarkup:
    if page.pending_delivery is not None:
        provider, index = page.pending_delivery
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [button("received", f"receipt:{page.workflow_id}")],
                [button("resend_confirm", f"resend:{page.workflow_id}:{provider}:{index}")],
                [button("search", f"uncertain_search:{page.workflow_id}")],
            ]
        )
    rows = []
    if retry_data is not None:
        rows.append([button("retry", retry_data)])
    versions = button(
        "another" if success or invalid else "back_list",
        f"subtitle:{page.workflow_id}:action:another",
    )
    change = button("language", f"nav:{page.workflow_id}:language")
    if page.total or page.candidates:
        rows.append([versions, change] if success else [versions])
        if not success:
            rows.append([change])
    else:
        rows.append([change])
    if page.is_episode:
        rows.append(
            [
                button(
                    "other_episode" if success else "back_episodes",
                    f"nav:{page.workflow_id}:episodes",
                )
            ]
        )
    elif not success:
        rows.append([button("back_titles", f"nav:{page.workflow_id}:titles")])
    rows.append([button("search", f"nav:{page.workflow_id}:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
