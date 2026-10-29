"""Subtitle-language selection never changes the interface language."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.dto import WorkflowStage
from app.bot.keyboards.common import button


def language_keyboard(
    workflow_id: str | None = None, *, stage: WorkflowStage = WorkflowStage.CHOOSING_SUBTITLE
) -> InlineKeyboardMarkup:
    prefix = f"language:{workflow_id}:" if workflow_id else "language:"
    rows = [
        [
            InlineKeyboardButton(text="فارسی", callback_data=f"{prefix}fa"),
            InlineKeyboardButton(text="English", callback_data=f"{prefix}en"),
        ]
    ]
    if workflow_id:
        if stage not in {WorkflowStage.IDLE, WorkflowStage.AWAITING_TITLE}:
            rows.append([button("back", f"nav:{workflow_id}:resume")])
        rows.append([button("search", f"nav:{workflow_id}:search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
