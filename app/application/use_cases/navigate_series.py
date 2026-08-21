"""Season and episode workflow transitions."""

from app.application.dto import (
    EpisodeSelectionOutcome,
    SeasonSelectionOutcome,
    WorkflowStage,
)
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.metadata import MetadataGateway
from app.application.use_cases.find_subtitles import FindSubtitles
from app.domain.errors import WorkflowExpiredError
from app.domain.models import SeasonSummary, SeriesRef, WorkflowId


class NavigateSeries:
    def __init__(
        self,
        conversations: ConversationRepository,
        metadata: MetadataGateway,
        find_subtitles: FindSubtitles,
        locks: UserLockManager,
    ) -> None:
        self._conversations = conversations
        self._metadata = metadata
        self._find_subtitles = find_subtitles
        self._locks = locks

    async def select_season(
        self, user_id: int, workflow_id: WorkflowId, season_number: int
    ) -> SeasonSelectionOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            series = conversation.selected_media
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_SEASON
                or not isinstance(series, SeriesRef)
                or not any(item.number == season_number for item in conversation.seasons)
            ):
                raise WorkflowExpiredError("That season has expired. Search again.")
            episodes = tuple(await self._metadata.episodes(series, season_number))
            await self._conversations.save(
                conversation.evolve(
                    stage=WorkflowStage.CHOOSING_EPISODE,
                    episodes=episodes,
                )
            )
            return SeasonSelectionOutcome(workflow_id, episodes)

    async def select_episode(
        self,
        user_id: int,
        workflow_id: WorkflowId,
        season_number: int,
        episode_number: int,
    ) -> EpisodeSelectionOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_EPISODE
            ):
                raise WorkflowExpiredError("That episode has expired. Search again.")
            episode = next(
                (
                    item
                    for item in conversation.episodes
                    if item.season_number == season_number and item.episode_number == episode_number
                ),
                None,
            )
            if episode is None:
                raise WorkflowExpiredError("That episode has expired. Search again.")
            updated = conversation.evolve(selected_media=episode, episodes=())
            page = await self._find_subtitles.find_for(updated)
            return EpisodeSelectionOutcome(workflow_id, episode, page)

    async def back_to_seasons(
        self, user_id: int, workflow_id: WorkflowId
    ) -> tuple[SeasonSummary, ...]:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if conversation.workflow_id != workflow_id or not conversation.seasons:
                raise WorkflowExpiredError("Those seasons have expired. Search again.")
            await self._conversations.save(
                conversation.evolve(stage=WorkflowStage.CHOOSING_SEASON, episodes=())
            )
            return conversation.seasons
