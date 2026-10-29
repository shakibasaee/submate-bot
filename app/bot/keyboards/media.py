"""Movie, season and episode choices with shared navigation."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.use_cases.navigate_series import NAVIGATION_PAGE_SIZE
from app.bot.keyboards.common import flow_controls, pagination
from app.bot.presentation import safe_button_text, truncate_text
from app.bot.texts import ui
from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MediaSearchResult, MediaType, SeasonSummary, WorkflowId


def result_label(result: MediaSearchResult) -> str:
    icon = "🎬" if result.media_type is MediaType.MOVIE else "📺"
    year = f" ({result.year})" if result.year else ""
    return safe_button_text(f"{icon} {truncate_text(result.title, 48)}{year}")


def results_keyboard(
    results: tuple[MediaSearchResult, ...] | list[MediaSearchResult],
    workflow_id: WorkflowId,
    offset: int = 0,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=result_label(item),
                callback_data=f"title:{workflow_id}:{item.media_type}:{item.external_id}",
            )
        ]
        for item in results[offset : offset + NAVIGATION_PAGE_SIZE]
    ]
    rows.extend(pagination(workflow_id, "t", len(results), offset, NAVIGATION_PAGE_SIZE))
    rows.extend(flow_controls(workflow_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def seasons_keyboard(
    seasons: tuple[SeasonSummary, ...] | list[SeasonSummary],
    workflow_id: WorkflowId,
    language: LanguageCode = LanguageCode.ENGLISH,
    offset: int = 0,
) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=safe_button_text(
                f"{ui('season')} {item.number:02d} · {truncate_text(item.name, 22)}"
            ),
            callback_data=f"season:{workflow_id}:{item.number}",
        )
        for item in seasons[offset : offset + NAVIGATION_PAGE_SIZE]
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.extend(pagination(workflow_id, "s", len(seasons), offset, NAVIGATION_PAGE_SIZE))
    rows.extend(flow_controls(workflow_id, "titles", "back_titles"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def episodes_keyboard(
    season_number: int,
    episode_numbers: tuple[int, ...],
    workflow_id: WorkflowId,
    language: LanguageCode = LanguageCode.ENGLISH,
    *,
    episodes: tuple[EpisodeRef, ...] = (),
    offset: int = 0,
) -> InlineKeyboardMarkup:
    names = {item.episode_number: item.name for item in episodes}
    buttons = [
        InlineKeyboardButton(
            text=safe_button_text(
                f"{number:02d} · {truncate_text(names.get(number, ui('episode')), 24)}"
            ),
            callback_data=f"episode:{workflow_id}:{season_number}:{number}",
        )
        for number in episode_numbers[offset : offset + NAVIGATION_PAGE_SIZE]
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.extend(pagination(workflow_id, "e", len(episode_numbers), offset, NAVIGATION_PAGE_SIZE))
    rows.extend(flow_controls(workflow_id, "back", "back_seasons"))
    return InlineKeyboardMarkup(inline_keyboard=rows)
