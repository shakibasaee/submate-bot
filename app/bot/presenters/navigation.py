"""Render a cached selection panel without new provider requests."""

from aiogram.types import Message

from app.application.dto import NavigationOutcome, WorkflowStage
from app.bot.keyboards.common import button
from app.bot.keyboards.media import episodes_keyboard, results_keyboard, seasons_keyboard
from app.bot.presentation import render_panel
from app.bot.texts import ui


async def send_navigation(
    message: Message,
    outcome: NavigationOutcome,
    *,
    edit: bool = False,
    error: str | None = None,
    retry_data: str | None = None,
) -> None:
    if outcome.stage is WorkflowStage.CHOOSING_TITLE:
        text = ui("titles") if outcome.results else ui("no_titles")
        markup = results_keyboard(outcome.results, outcome.workflow_id, outcome.offset)
    elif outcome.stage is WorkflowStage.CHOOSING_EPISODE:
        text = ui("episodes") if outcome.episodes else ui("no_episodes")
        markup = episodes_keyboard(
            outcome.episodes[0].season_number if outcome.episodes else 1,
            tuple(item.episode_number for item in outcome.episodes),
            outcome.workflow_id,
            episodes=outcome.episodes,
            offset=outcome.offset,
        )
    else:
        text = ui("seasons")
        markup = seasons_keyboard(outcome.seasons, outcome.workflow_id, offset=outcome.offset)
    if retry_data:
        markup.inline_keyboard.insert(0, [button("retry", retry_data)])
    await render_panel(message, f"{error}\n\n{text}" if error else text, markup, edit=edit)
