"""Thin Telegram adapters for title and TV navigation workflows."""

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.application.container import ApplicationServices
from app.bot.keyboards.media import (
    episodes_keyboard,
    result_label,
    results_keyboard,
    seasons_keyboard,
)
from app.bot.presentation import remove_inline_keyboard, safe_html_text
from app.bot.presenters.errors import present_error
from app.bot.presenters.subtitles import send_subtitle_page
from app.core.logging import user_reference
from app.domain.errors import ApplicationError
from app.domain.models import MediaType, MovieRef, WorkflowId

router = Router(name=__name__)
logger = structlog.get_logger(__name__)


@router.message(F.text & ~F.text.startswith("/"))
async def title_search(message: Message, services: ApplicationServices) -> None:
    if message.from_user is None or message.text is None:
        return
    try:
        outcome = await services.search_titles.execute(message.from_user.id, message.text)
    except ApplicationError as error:
        await message.answer(present_error(error))
        return
    if not outcome.results:
        await message.answer("No movie or TV series matched that title. Try a different search.")
        return
    logger.info(
        "title_search_completed",
        user_ref=user_reference(message.from_user.id),
        result_count=len(outcome.results),
    )
    await message.answer(
        "Which title did you mean?",
        reply_markup=results_keyboard(outcome.results, outcome.workflow_id),
    )


@router.callback_query(F.data.startswith("title:"))
async def title_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 3)
    if len(parts) != 4 or parts[2] not in {"movie", "tv"} or not parts[3]:
        await callback.answer("That title selection is invalid.", show_alert=True)
        return
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    await remove_inline_keyboard(message)
    try:
        outcome = await services.select_title.execute(
            callback.from_user.id,
            WorkflowId(parts[1]),
            MediaType(parts[2]),
            parts[3],
        )
    except ApplicationError as error:
        await message.answer(present_error(error))
        return
    if isinstance(outcome.selected, MovieRef):
        await message.answer(f"Selected: {safe_html_text(outcome.selected.title, 500)}")
        if outcome.subtitle_page is None:
            await message.answer("No subtitles found. Try another title.")
            return
        await send_subtitle_page(
            message,
            outcome.subtitle_page,
            title=outcome.selected.title,
            language=outcome.subtitle_page.language,
        )
        return
    if not outcome.seasons:
        await message.answer(
            "This series has no regular seasons available. Specials (Season 0) are not selectable."
        )
        return
    await message.answer(
        "Choose a season:\nSpecials (Season 0) are not selectable.",
        reply_markup=seasons_keyboard(outcome.seasons, outcome.workflow_id),
    )


@router.callback_query(F.data.startswith("season:"))
async def season_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("That season selection is invalid.", show_alert=True)
        return
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    await remove_inline_keyboard(message)
    try:
        outcome = await services.navigate_series.select_season(
            callback.from_user.id, WorkflowId(parts[1]), int(parts[2])
        )
    except ApplicationError as error:
        await message.answer(present_error(error))
        return
    if not outcome.episodes:
        await message.answer("This season has no episodes available.")
        return
    season_number = outcome.episodes[0].season_number
    await message.answer(
        "Choose an episode:",
        reply_markup=episodes_keyboard(
            season_number,
            tuple(item.episode_number for item in outcome.episodes),
            outcome.workflow_id,
        ),
    )


@router.callback_query(F.data.startswith("episode:"))
async def episode_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 3)
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("That episode selection is invalid.", show_alert=True)
        return
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    await remove_inline_keyboard(message)
    try:
        outcome = await services.navigate_series.select_episode(
            callback.from_user.id,
            WorkflowId(parts[1]),
            int(parts[2]),
            int(parts[3]),
        )
    except ApplicationError as error:
        await message.answer(present_error(error))
        return
    await message.answer(f"Selected episode: {safe_html_text(outcome.episode.name, 500)}")
    await send_subtitle_page(
        message,
        outcome.subtitle_page,
        title=outcome.episode.series.title,
        language=outcome.subtitle_page.language,
    )


@router.callback_query(F.data.startswith("nav:"))
async def navigation_action(callback: CallbackQuery, services: ApplicationServices) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or parts[2] not in {"back", "cancel"}:
        await callback.answer("That navigation action is invalid.", show_alert=True)
        return
    await callback.answer("Cancelled." if parts[2] == "cancel" else None)
    message = callback.message
    if isinstance(message, Message):
        await remove_inline_keyboard(message)
    try:
        if parts[2] == "cancel":
            await services.cancel_workflow.execute(callback.from_user.id)
            if isinstance(message, Message):
                await message.answer(
                    "Current action cancelled. Use /language when you are ready to search."
                )
            return
        seasons = await services.navigate_series.back_to_seasons(
            callback.from_user.id, WorkflowId(parts[1])
        )
    except ApplicationError as error:
        if isinstance(message, Message):
            await message.answer(present_error(error))
        return
    if isinstance(message, Message):
        await message.answer(
            "Choose a season:",
            reply_markup=seasons_keyboard(seasons, WorkflowId(parts[1])),
        )


__all__ = [
    "episodes_keyboard",
    "result_label",
    "results_keyboard",
    "seasons_keyboard",
    "title_selected",
]
