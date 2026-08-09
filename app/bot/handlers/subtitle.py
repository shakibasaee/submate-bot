"""Subtitle search, selection, validation, and safe Telegram delivery."""

import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramServerError
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.state import SubtitleResult, conversation_store
from app.core.config import get_settings
from app.core.infrastructure import infrastructure
from app.core.logging import user_reference
from app.core.monitoring import monitoring
from app.core.retry import retry_async
from app.services.opensubtitles import (
    OpenSubtitlesClient,
    OpenSubtitlesError,
    OpenSubtitlesLinkError,
    OpenSubtitlesQuotaError,
    UnsafeSubtitleError,
)

router = Router(name=__name__)
logger = structlog.get_logger(__name__)
PAGE_SIZE = 5
PROVIDER_NOTICE = (
    "Provided by OpenSubtitles.com. Subtitle copyright belongs to its respective author."
)


def delivery_filename(title: str, language: str, season: int | None, episode: int | None) -> str:
    """Create a readable Telegram filename without unsafe filesystem characters."""
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title)
    safe_title = re.sub(r"\s+", " ", safe_title).strip(" .")[:70] or "subtitle"
    episode_label = ""
    if season is not None and episode is not None:
        episode_label = f"-S{season:02d}E{episode:02d}"
    return f"{safe_title}{episode_label}-{language}.srt"


@contextmanager
def temporary_srt(content: bytes) -> Iterator[Path]:
    """Write an SRT for Telegram and guarantee deletion on every exit path."""
    descriptor, name = tempfile.mkstemp(prefix="subtitle-", suffix=".srt")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
        yield path
    finally:
        path.unlink(missing_ok=True)


async def deliver_subtitle(message: Message, user_id: int, result: SubtitleResult) -> None:
    """Retrieve, validate, send, and immediately delete a selected subtitle."""
    conversation = conversation_store.get(user_id)
    if result.format != "srt":
        await message.answer("That result is not an SRT file and cannot be delivered safely.")
        return
    key = get_settings().opensubtitles_api_key
    if key is None or key.get_secret_value().startswith("replace-"):
        await message.answer("Subtitle delivery is not configured yet. Please try again later.")
        return
    if not await infrastructure.allow(
        "user-subtitle-download", user_id, infrastructure.user_download_limit, 600
    ):
        await message.answer("Too many download attempts. Please wait before trying again.")
        return
    if not await infrastructure.allow(
        "global-subtitle-download", "all", infrastructure.global_download_limit, 60
    ):
        await message.answer("Subtitle downloads are busy right now. Please try again shortly.")
        return

    client = OpenSubtitlesClient(key.get_secret_value())
    try:
        link = await client.request_download_link(result.file_id)
        content = await client.download_srt(link)
    except OpenSubtitlesQuotaError:
        await message.answer(
            "OpenSubtitles has reached its download quota or rate limit. Please try again later."
        )
        return
    except OpenSubtitlesLinkError:
        monitoring.increment("delivery_errors", "opensubtitles")
        await message.answer(
            "The temporary subtitle link expired or the download failed. Select the result again "
            "to retry."
        )
        return
    except UnsafeSubtitleError:
        monitoring.increment("unsafe_files_rejected", "opensubtitles")
        await message.answer(
            "That file was rejected because it was unsafe, oversized, corrupt, or not a valid SRT."
        )
        return
    except OpenSubtitlesError:
        await message.answer("Subtitle delivery failed safely. Please try again later.")
        return

    language = str(conversation.language or "subtitle")
    filename = delivery_filename(
        conversation.selected_title or "subtitle",
        language,
        conversation.selected_season_number,
        conversation.selected_episode_number,
    )
    uploader = f"\nUploader: {result.uploader}" if result.uploader else ""
    try:
        with temporary_srt(content) as path:
            document = FSInputFile(path, filename=filename)
            await retry_async(
                lambda: message.answer_document(
                    document,
                    caption=f"{PROVIDER_NOTICE}{uploader}",
                ),
                (TelegramNetworkError, TelegramServerError),
                attempts=3,
            )
            monitoring.increment("deliveries", "telegram")
            logger.info("subtitle_delivered", user_ref=user_reference(user_id))
    except (OSError, TelegramAPIError):
        monitoring.increment("delivery_errors", "telegram")
        await message.answer("The subtitle could not be prepared or sent. Please try again.")


def subtitle_label(result: SubtitleResult) -> str:
    """Keep a subtitle choice focused on useful compatibility distinctions."""
    labels = [result.release, result.format.upper()]
    if result.hearing_impaired:
        labels.append("HI")
    if result.download_count is not None:
        labels.append(f"↓{result.download_count}")
    if result.rating is not None:
        labels.append(f"★{result.rating:g}")
    return " — ".join(labels)


def subtitle_keyboard(results: list[SubtitleResult], offset: int = 0) -> InlineKeyboardMarkup:
    """Render a bounded page, with language change and cancellation controls."""
    page = results[offset : offset + PAGE_SIZE]
    rows = [
        [
            InlineKeyboardButton(
                text=subtitle_label(result), callback_data=f"subtitle:{result.file_id}"
            )
        ]
        for result in page
    ]
    if offset + PAGE_SIZE < len(results):
        rows.append([InlineKeyboardButton(text="More results", callback_data="subtitle:more")])
    rows.append(
        [
            InlineKeyboardButton(text="Change language", callback_data="subtitle:language"),
            InlineKeyboardButton(text="Cancel", callback_data="subtitle:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def search_subtitles(message: Message, user_id: int) -> None:
    """Search for the user's exact selected movie or TV episode."""
    conversation = conversation_store.get(user_id)
    settings = get_settings()
    key = settings.opensubtitles_api_key
    if key is None or key.get_secret_value().startswith("replace-"):
        await message.answer("Subtitle search is not configured yet. Please try again later.")
        return
    if conversation.selected_tmdb_id is None or conversation.language is None:
        await message.answer("That title selection has expired. Search again.")
        return
    if not await infrastructure.allow(
        "user-subtitle-search", user_id, infrastructure.user_search_limit, 60
    ):
        await message.answer("Too many subtitle searches. Please wait a minute and try again.")
        return
    if not await infrastructure.allow(
        "global-subtitle-search", "all", infrastructure.global_subtitle_limit, 60
    ):
        await message.answer("Subtitle search is busy right now. Please try again shortly.")
        return
    try:
        results = await OpenSubtitlesClient(key.get_secret_value()).search(
            tmdb_id=conversation.selected_tmdb_id,
            language=str(conversation.language),
            season_number=conversation.selected_season_number,
            episode_number=conversation.selected_episode_number,
        )
    except OpenSubtitlesError:
        await message.answer(
            "Subtitle search is temporarily unavailable or quota-limited. Try again later."
        )
        return
    if not results:
        await message.answer(
            "No subtitles found. Try /language, search a different title, or try again later."
        )
        return
    conversation_store.set_subtitle_results(user_id, results)
    logger.info(
        "subtitle_search_completed",
        user_ref=user_reference(user_id),
        result_count=len(results),
        language=str(conversation.language),
    )
    language = "English" if str(conversation.language) == "en" else "Persian"
    title = conversation.selected_title or "this title"
    await message.answer(
        f"Choose a subtitle version for {title}, {language}:",
        reply_markup=subtitle_keyboard(results),
    )


@router.callback_query(F.data.startswith("subtitle:"))
async def subtitle_selected(callback: CallbackQuery) -> None:
    """Select a validated provider result and deliver its safe SRT file."""
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    action = callback.data.removeprefix("subtitle:")
    conversation = conversation_store.get(callback.from_user.id)
    if action == "cancel":
        conversation_store.cancel(callback.from_user.id)
        await callback.answer("Cancelled.")
        return
    if action == "language":
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer("Use /language to change the subtitle language.")
        return
    if action == "more":
        results = list((conversation.subtitle_results or {}).values())
        next_offset = conversation.subtitle_offset + PAGE_SIZE
        if next_offset >= len(results) or callback.message is None:
            await callback.answer("No more results.", show_alert=True)
            return
        conversation.subtitle_offset = next_offset
        await callback.answer()
        await callback.message.answer(
            "More subtitle results:", reply_markup=subtitle_keyboard(results, next_offset)
        )
        return
    if not action.isdigit():
        await callback.answer("That subtitle selection is invalid.", show_alert=True)
        return
    result = conversation_store.select_subtitle(callback.from_user.id, int(action))
    if result is None:
        await callback.answer("That subtitle result has expired. Search again.", show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(f"Selected: {subtitle_label(result)}. Preparing the file…")
        await deliver_subtitle(callback.message, callback.from_user.id, result)
