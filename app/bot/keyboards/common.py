"""Shared controls and real pagination for every inline selection panel."""

from aiogram.types import InlineKeyboardButton

from app.bot.texts import ui
from app.domain.models import WorkflowId


def button(key: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=ui(key), callback_data=data)


def flow_controls(
    workflow_id: WorkflowId, back: str | None = None, back_label: str = "back"
) -> list[list[InlineKeyboardButton]]:
    rows = [[button(back_label, f"nav:{workflow_id}:{back}")]] if back else []
    rows.append(
        [
            button("language", f"nav:{workflow_id}:language"),
            button("search", f"nav:{workflow_id}:search"),
        ]
    )
    return rows


def pagination(
    workflow_id: WorkflowId, kind: str, total: int, offset: int, size: int
) -> list[list[InlineKeyboardButton]]:
    if total <= size:
        return []
    page = offset // size
    count = (total + size - 1) // size
    row = []
    if page:
        row.append(button("previous", f"page:{workflow_id}:{kind}:{page - 1}"))
    row.append(
        InlineKeyboardButton(
            text=f"{page + 1} / {count}", callback_data=f"page:{workflow_id}:info:{page}"
        )
    )
    if page + 1 < count:
        row.append(button("next", f"page:{workflow_id}:{kind}:{page + 1}"))
    return [row]
