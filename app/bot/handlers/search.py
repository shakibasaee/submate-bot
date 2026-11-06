"""Title selection and cached, paginated inline navigation."""

from contextlib import suppress

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramServerError
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from app.application.container import ApplicationServices
from app.application.dto import NavigationOutcome, WorkflowStage
from app.application.use_cases.download_season import SeasonPackUnavailable
from app.application.use_cases.navigate_series import NAVIGATION_PAGE_SIZE
from app.bot.handlers.language import show_language_picker
from app.bot.keyboards.common import button, flow_controls
from app.bot.keyboards.media import (
    episodes_keyboard,
    result_label,
    results_keyboard,
    seasons_keyboard,
)
from app.bot.presentation import answer_callback, render_panel, safe_caption
from app.bot.presenters.errors import present_error
from app.bot.presenters.navigation import send_navigation
from app.bot.presenters.subtitles import send_subtitle_page
from app.bot.presenters.workflow import recover_workflow, show_workflow
from app.bot.texts import subtitle_language_label, ui
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
        # A first-time user can choose the subtitle language directly.
        if "Choose a subtitle language" in str(error):
            picker = await services.choose_language.open_picker(message.from_user.id)
            await show_language_picker(message, str(picker.workflow_id), stage=picker.stage)
        else:
            await message.answer(present_error(error))
        return
    logger.info(
        "title_search_completed",
        user_ref=user_reference(message.from_user.id),
        result_count=len(outcome.results),
    )
    await send_navigation(
        message,
        NavigationOutcome(
            outcome.workflow_id,
            # Subtitle language is not used to choose interface labels.
            language=outcome.language,
            stage=WorkflowStage.CHOOSING_TITLE,
            results=outcome.results,
        ),
        error=ui("similar_titles") if outcome.suggested else None,
    )


@router.callback_query(F.data.startswith("title:"))
async def title_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        await answer_callback(callback)
        return
    parts = callback.data.split(":")
    if len(parts) != 4 or parts[2] not in {"movie", "tv"}:
        await answer_callback(callback, ui("stale"))
        return
    await answer_callback(callback)
    workflow = WorkflowId(parts[1])
    try:
        outcome = await services.select_title.execute(
            callback.from_user.id, workflow, MediaType(parts[2]), parts[3]
        )
        if isinstance(outcome.selected, MovieRef) and outcome.subtitle_page is not None:
            await send_subtitle_page(
                callback.message,
                outcome.subtitle_page,
                title=outcome.selected.title,
                language=outcome.subtitle_page.language,
                edit=True,
            )
        else:
            nav = await services.navigate_series.current_navigation(callback.from_user.id, workflow)
            await show_workflow(callback.message, services, callback.from_user.id, nav)
    except ApplicationError as error:
        await recover_workflow(callback, services, workflow, error)


@router.callback_query(F.data.startswith("season:"))
async def season_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit() or not isinstance(callback.message, Message):
        await answer_callback(callback, ui("stale"))
        return
    await answer_callback(callback)
    workflow = WorkflowId(parts[1])
    try:
        await services.navigate_series.select_season(callback.from_user.id, workflow, int(parts[2]))
        nav = await services.navigate_series.current_navigation(callback.from_user.id, workflow)
        await show_workflow(callback.message, services, callback.from_user.id, nav)
    except ApplicationError as error:
        await recover_workflow(callback, services, workflow, error)


@router.callback_query(F.data.startswith("pack:"))
async def season_pack_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    service = services.download_season
    if service is None or not callback.data or not isinstance(callback.message, Message):
        await answer_callback(callback, ui("stale"))
        return
    user_id = callback.from_user.id
    workflow_id = WorkflowId(callback.data.partition(":")[2])
    try:
        state = await service.claim(user_id, workflow_id)
    except ApplicationError as error:
        await answer_callback(callback, present_error(error))
        return
    message = callback.message
    error_text = None
    uncertain = False
    try:
        await answer_callback(callback)
        with suppress(TelegramAPIError):
            await render_panel(message, ui("season_pack_working"), edit=True)
        try:
            content = await service.build(state)
        except SeasonPackUnavailable:
            error_text = ui("season_pack_missing")
        except ApplicationError as error:
            error_text = present_error(error)
        else:
            season = state.episodes[0].season_number
            try:
                await message.answer_document(
                    BufferedInputFile(
                        content, filename=f"SubMate-S{season:02d}-{state.language}.zip"
                    ),
                    caption=safe_caption(
                        ui("season_pack_ready").format(
                            season=season,
                            count=len(state.episodes),
                            language=subtitle_language_label(state.language),
                        )
                    ),
                )
            except (TelegramNetworkError, TelegramServerError, TimeoutError):
                uncertain = True
                error_text = ui("season_pack_uncertain")
            except TelegramAPIError:
                error_text = ui("upload_failed")
    finally:
        next_workflow = await service.finish(state)
    if error_text is None:
        with suppress(TelegramAPIError):
            await message.edit_text(ui("season_pack_sent"), reply_markup=None)
    try:
        nav = await services.navigate_series.current_navigation(
            user_id, next_workflow, rotate=False
        )
    except ApplicationError:
        return
    if error_text is None:
        rows = flow_controls(nav.workflow_id, "resume", "season_pack_back_episodes")
        rows.insert(1, [button("back_seasons", f"nav:{nav.workflow_id}:back")])
        await message.answer(
            ui("season_pack_next"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        return
    await send_navigation(
        message,
        nav,
        edit=True,
        error=error_text,
        season_pack_limit=0 if uncertain else service.max_episodes,
    )


@router.callback_query(F.data.startswith("episode:"))
async def episode_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    parts = (callback.data or "").split(":")
    if (
        len(parts) != 4
        or not all(p.isdigit() for p in parts[2:])
        or not isinstance(callback.message, Message)
    ):
        await answer_callback(callback, ui("stale"))
        return
    await answer_callback(callback)
    workflow = WorkflowId(parts[1])
    try:
        outcome = await services.navigate_series.select_episode(
            callback.from_user.id, workflow, int(parts[2]), int(parts[3])
        )
        await send_subtitle_page(
            callback.message,
            outcome.subtitle_page,
            title=outcome.episode.series.title,
            language=outcome.subtitle_page.language,
            edit=True,
        )
    except ApplicationError as error:
        await recover_workflow(callback, services, workflow, error)


@router.callback_query(F.data.startswith("nav:"))
async def navigation_action(callback: CallbackQuery, services: ApplicationServices) -> None:
    parts = (callback.data or "").split(":")
    if (
        len(parts) != 3
        or parts[2] not in {"back", "episodes", "titles", "resume", "cancel", "language", "search"}
        or not isinstance(callback.message, Message)
    ):
        await answer_callback(callback, ui("stale"))
        return
    workflow, action = WorkflowId(parts[1]), parts[2]
    await answer_callback(callback)
    try:
        if action in {"search", "cancel"}:
            result = await services.start_search.execute(callback.from_user.id, workflow)
            if result.language is None:
                await show_language_picker(
                    callback.message, str(result.workflow_id), stage=WorkflowStage.IDLE, edit=True
                )
            else:
                assert result.workflow_id is not None
                await render_panel(
                    callback.message,
                    ui("title"),
                    InlineKeyboardMarkup(inline_keyboard=flow_controls(result.workflow_id)),
                    edit=True,
                )
            return
        if action == "language":
            picker = await services.choose_language.open_picker(callback.from_user.id, workflow)
            await show_language_picker(
                callback.message, str(picker.workflow_id), stage=picker.stage, edit=True
            )
            return
        methods = {
            "back": services.navigate_series.back_to_seasons,
            "episodes": services.navigate_series.back_to_episodes,
            "titles": services.navigate_series.back_to_titles,
            "resume": services.navigate_series.current_navigation,
        }
        outcome = await methods[action](callback.from_user.id, workflow)
        await show_workflow(callback.message, services, callback.from_user.id, outcome)
    except ApplicationError as error:
        await recover_workflow(callback, services, workflow, error)


@router.callback_query(F.data.startswith("page:"))
async def page_selected(callback: CallbackQuery, services: ApplicationServices) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[3].isdigit() or not isinstance(callback.message, Message):
        await answer_callback(callback, ui("stale"))
        return
    workflow, kind, page = WorkflowId(parts[1]), parts[2], int(parts[3])
    await answer_callback(callback)
    try:
        if kind == "info":
            await services.navigate_series.current_navigation(
                callback.from_user.id, workflow, rotate=False
            )
            return
        if kind == "u":
            outcome = await services.find_subtitles.page_at(
                callback.from_user.id, workflow, page * 5
            )
            await send_subtitle_page(
                callback.message, outcome, title="this title", language=outcome.language, edit=True
            )
        elif kind in {"t", "s", "e"}:
            stage = {
                "t": WorkflowStage.CHOOSING_TITLE,
                "s": WorkflowStage.CHOOSING_SEASON,
                "e": WorkflowStage.CHOOSING_EPISODE,
            }[kind]
            nav = await services.navigate_series.page_at(
                callback.from_user.id, workflow, stage, page * NAVIGATION_PAGE_SIZE
            )
            await show_workflow(callback.message, services, callback.from_user.id, nav)
        else:
            await answer_callback(callback, ui("stale"))
    except ApplicationError as error:
        await recover_workflow(callback, services, workflow, error)


__all__ = [
    "episodes_keyboard",
    "result_label",
    "results_keyboard",
    "seasons_keyboard",
    "title_selected",
]
