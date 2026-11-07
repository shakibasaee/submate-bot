"""Subtitle-language selection never changes the interface language."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.dto import WorkflowStage
from app.bot.keyboards.common import button
from app.domain.languages import LANGUAGE_NAMES, LanguageCode


def language_keyboard(
    workflow_id: str | None = None,
    *,
    stage: WorkflowStage = WorkflowStage.CHOOSING_SUBTITLE,
    matches: tuple[LanguageCode, ...] | None = None,
) -> InlineKeyboardMarkup:
    prefix = f"language:{workflow_id}:" if workflow_id else "language:"
    codes = tuple(LANGUAGE_NAMES) if matches is None else matches
    buttons = [
        InlineKeyboardButton(text=LANGUAGE_NAMES[code][0], callback_data=f"{prefix}{code}")
        for code in codes
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    if workflow_id:
        if stage not in {WorkflowStage.IDLE, WorkflowStage.AWAITING_TITLE}:
            rows.append([button("back", f"nav:{workflow_id}:resume")])
        rows.append([button("search", f"nav:{workflow_id}:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
