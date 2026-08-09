"""TMDb title search and result-selection handlers."""

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.handlers.subtitle import search_subtitles
from app.bot.presentation import remove_inline_keyboard, safe_button_text, safe_html_text
from app.bot.state import Episode, MediaType, SearchResult, Season, conversation_store
from app.core.config import get_settings
from app.core.infrastructure import infrastructure
from app.core.logging import user_reference
from app.services.tmdb import TmdbClient, TmdbSearchError

router = Router(name=__name__)
logger = structlog.get_logger(__name__)

MIN_QUERY_LENGTH = 2
MAX_NAVIGATION_BUTTONS = 50


def result_label(result: SearchResult) -> str:
    """Format a compact, unambiguous label for a title button."""
    icon = "🎬" if result.media_type is MediaType.MOVIE else "📺"
    kind = "TV" if result.media_type is MediaType.TV else None
    details = ", ".join(part for part in (kind, result.year) if part)
    return safe_button_text(f"{icon} {result.title}" + (f" ({details})" if details else ""))


def results_keyboard(results: list[SearchResult], workflow_id: int) -> InlineKeyboardMarkup:
    """Build one callback-safe button per bounded result."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=result_label(result),
                    callback_data=(f"title:{workflow_id}:{result.media_type}:{result.tmdb_id}"),
                )
            ]
            for result in results
        ]
    )


def seasons_keyboard(seasons: list[Season], workflow_id: int) -> InlineKeyboardMarkup:
    """Build a compact two-column season picker with a cancel action."""
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
    season_number: int, episodes: list[Episode], workflow_id: int
) -> InlineKeyboardMarkup:
    """Build a compact episode picker with back and cancel actions."""
    buttons = [
        InlineKeyboardButton(
            text=f"Episode {episode.number}",
            callback_data=(f"episode:{workflow_id}:{season_number}:{episode.number}"),
        )
        for episode in episodes[:MAX_NAVIGATION_BUTTONS]
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    rows.append(
        [
            InlineKeyboardButton(text="Back", callback_data=f"nav:{workflow_id}:back"),
            InlineKeyboardButton(text="Cancel", callback_data=f"nav:{workflow_id}:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tmdb_client() -> TmdbClient | None:
    """Create a configured client without ever exposing the API key."""
    api_key = get_settings().tmdb_api_key
    if api_key is None or api_key.get_secret_value().startswith("replace-"):
        return None
    return TmdbClient(api_key.get_secret_value())


@router.message(F.text & ~F.text.startswith("/"))
async def title_search(message: Message) -> None:
    """Search TMDb after a user has selected their subtitle language."""
    if message.from_user is None or message.text is None:
        return
    conversation = conversation_store.get(message.from_user.id)
    workflow_id = conversation.workflow_id
    query = message.text.strip()
    if conversation.language is None:
        await message.answer("Choose a subtitle language first with /language.")
        return
    if not conversation.awaiting_title:
        await message.answer("Use /language to start a subtitle search.")
        return
    if not query:
        await message.answer("Send the name of a movie or TV series to search.")
        return
    if len(query) < MIN_QUERY_LENGTH:
        await message.answer("Please enter at least 2 characters for the title.")
        return
    client = tmdb_client()
    if client is None:
        await message.answer("Title search is not configured yet. Please try again later.")
        return
    if not await infrastructure.allow(
        "user-title-search", message.from_user.id, infrastructure.user_search_limit, 60
    ):
        await message.answer("Too many searches. Please wait a minute and try again.")
        return
    if not await infrastructure.allow("global-tmdb", "all", infrastructure.global_tmdb_limit, 60):
        await message.answer("Title search is busy right now. Please try again shortly.")
        return
    try:
        results = await client.search(query)
    except TmdbSearchError:
        await message.answer("I could not search titles right now. Please try again shortly.")
        return
    if not results:
        await message.answer("No movie or TV series matched that title. Try a different search.")
        return
    if not conversation_store.set_search_results(message.from_user.id, workflow_id, results):
        await message.answer("That search was cancelled. Start again when you are ready.")
        return
    logger.info(
        "title_search_completed",
        user_ref=user_reference(message.from_user.id),
        result_count=len(results),
    )
    await message.answer(
        "Which title did you mean?",
        reply_markup=results_keyboard(results, workflow_id),
    )


@router.callback_query(F.data.startswith("title:"))
async def title_selected(callback: CallbackQuery) -> None:
    """Validate a selected result against the user's latest displayed choices."""
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if (
        len(parts) != 4
        or not parts[1].isdigit()
        or parts[2] not in {"movie", "tv"}
        or not parts[3].isdigit()
    ):
        await callback.answer("That title selection is invalid.", show_alert=True)
        return
    workflow_id = int(parts[1])
    result = conversation_store.select_result(
        callback.from_user.id, workflow_id, MediaType(parts[2]), int(parts[3])
    )
    if result is None:
        await callback.answer("That result has expired. Search again.", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await remove_inline_keyboard(callback.message)
    if not isinstance(callback.message, Message):
        return
    if result.media_type is MediaType.MOVIE:
        await callback.message.answer(f"Selected: {safe_html_text(result_label(result))}")
        await search_subtitles(callback.message, callback.from_user.id)
        return
    client = tmdb_client()
    if client is None:
        await callback.message.answer(
            "TV navigation is not configured yet. Please try again later."
        )
        return
    try:
        seasons = await client.seasons(result.tmdb_id)
    except TmdbSearchError:
        await callback.message.answer(
            "I could not load seasons right now. Please try again shortly."
        )
        return
    if not seasons:
        await callback.message.answer(
            "This series has no regular seasons available. Specials (Season 0) are not selectable."
        )
        return
    if not conversation_store.set_seasons(callback.from_user.id, workflow_id, seasons):
        await callback.message.answer("That selection expired. Start again.")
        return
    await callback.message.answer(
        "Choose a season:\nSpecials (Season 0) are not selectable.",
        reply_markup=seasons_keyboard(seasons, workflow_id),
    )


@router.callback_query(F.data.startswith("season:"))
async def season_selected(callback: CallbackQuery) -> None:
    """Load actual episodes for a displayed selected season."""
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await callback.answer("That season selection is invalid.", show_alert=True)
        return
    workflow_id = int(parts[1])
    season_number = int(parts[2])
    if conversation_store.select_season(callback.from_user.id, workflow_id, season_number) is None:
        await callback.answer("That season has expired. Search again.", show_alert=True)
        return
    conversation = conversation_store.get(callback.from_user.id)
    if conversation.selected_tmdb_id is None or callback.message is None:
        await callback.answer("That series selection has expired.", show_alert=True)
        return
    await callback.answer()
    await remove_inline_keyboard(callback.message)
    client = tmdb_client()
    if client is None:
        await callback.message.answer(
            "TV navigation is not configured yet. Please try again later."
        )
        return
    try:
        episodes = await client.episodes(conversation.selected_tmdb_id, season_number)
    except TmdbSearchError:
        await callback.message.answer(
            "I could not load episodes right now. Please try again shortly."
        )
        return
    if not episodes:
        await callback.message.answer("This season has no episodes available.")
        return
    if not conversation_store.set_episodes(callback.from_user.id, workflow_id, episodes):
        await callback.message.answer("That selection expired. Start again.")
        return
    await callback.message.answer(
        "Choose an episode:",
        reply_markup=episodes_keyboard(season_number, episodes, workflow_id),
    )


@router.callback_query(F.data.startswith("episode:"))
async def episode_selected(callback: CallbackQuery) -> None:
    """Validate and store a complete series/season/episode selection."""
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if (
        len(parts) != 4
        or not parts[1].isdigit()
        or not parts[2].isdigit()
        or not parts[3].isdigit()
    ):
        await callback.answer("That episode selection is invalid.", show_alert=True)
        return
    workflow_id = int(parts[1])
    episode = conversation_store.select_episode(
        callback.from_user.id,
        workflow_id,
        int(parts[2]),
        int(parts[3]),
    )
    if episode is None:
        await callback.answer("That episode has expired. Search again.", show_alert=True)
        return
    await callback.answer()
    message = callback.message
    if isinstance(message, Message):
        await remove_inline_keyboard(message)
        await message.answer(f"Selected episode: {safe_html_text(episode.name, 500)}")
        await search_subtitles(message, callback.from_user.id)


@router.callback_query(F.data.startswith("nav:"))
async def navigation_action(callback: CallbackQuery) -> None:
    """Handle safe in-keyboard back and cancel actions."""
    if callback.from_user is None:
        await callback.answer()
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in {"back", "cancel"}:
        await callback.answer("That navigation action is invalid.", show_alert=True)
        return
    workflow_id = int(parts[1])
    if not conversation_store.is_active(callback.from_user.id, workflow_id):
        await callback.answer("That selection has expired. Start again.", show_alert=True)
        return
    if parts[2] == "cancel":
        conversation_store.cancel(callback.from_user.id)
        await callback.answer("Cancelled.")
        if callback.message is not None:
            await remove_inline_keyboard(callback.message)
            await callback.message.answer(
                "Current action cancelled. Use /language when you are ready to search."
            )
        return
    if not conversation_store.back_to_seasons(callback.from_user.id, workflow_id):
        await callback.answer("Those seasons have expired. Search again.", show_alert=True)
        return
    stored_seasons = conversation_store.get(callback.from_user.id).seasons
    if not stored_seasons:
        await callback.answer("Those seasons have expired. Search again.", show_alert=True)
        return
    seasons = list(stored_seasons.values())
    await callback.answer()
    if callback.message is not None:
        await remove_inline_keyboard(callback.message)
        await callback.message.answer(
            "Choose a season:", reply_markup=seasons_keyboard(seasons, workflow_id)
        )
