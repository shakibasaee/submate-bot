"""Movie, season, and episode keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.presentation import safe_button_text
from app.domain.models import MediaSearchResult, MediaType, SeasonSummary, WorkflowId

MAX_NAVIGATION_BUTTONS = 50


def result_label(result: MediaSearchResult) -> str:
    icon = "🎬" if result.media_type is MediaType.MOVIE else "📺"
    kind = "TV" if result.media_type is MediaType.TV else None
    details = ", ".join(part for part in (kind, result.year) if part)
    return safe_button_text(f"{icon} {result.title}" + (f" ({details})" if details else ""))


def results_keyboard(
    results: tuple[MediaSearchResult, ...] | list[MediaSearchResult], workflow_id: WorkflowId
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=result_label(result),
                    callback_data=(f"title:{workflow_id}:{result.media_type}:{result.external_id}"),
                )
            ]
            for result in results
        ]
    )


def seasons_keyboard(
    seasons: tuple[SeasonSummary, ...] | list[SeasonSummary], workflow_id: WorkflowId
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"Season {season.number}",
            callback_data=f"season:{workflow_id}:{season.number}",
        )
        for season in seasons[:MAX_NAVIGATION_BUTTONS]
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="Cancel", callback_data=f"nav:{workflow_id}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def episodes_keyboard(
    season_number: int,
    episode_numbers: tuple[int, ...],
    workflow_id: WorkflowId,
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"Episode {number}",
            callback_data=f"episode:{workflow_id}:{season_number}:{number}",
        )
        for number in episode_numbers[:MAX_NAVIGATION_BUTTONS]
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(text="Back", callback_data=f"nav:{workflow_id}:back"),
            InlineKeyboardButton(text="Cancel", callback_data=f"nav:{workflow_id}:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
