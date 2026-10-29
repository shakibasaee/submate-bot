"""Season and episode workflow transitions."""

from uuid import uuid4

from app.application.dto import (
    Conversation,
    EpisodeSelectionOutcome,
    NavigationOutcome,
    SeasonSelectionOutcome,
    WorkflowStage,
)
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.metadata import MetadataGateway
from app.application.use_cases.find_subtitles import FindSubtitles
from app.domain.errors import ApplicationError, WorkflowExpiredError
from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, SeriesRef, WorkflowId

NAVIGATION_PAGE_SIZE = 8


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
            try:
                episodes = tuple(await self._metadata.episodes(series, season_number))
            except ApplicationError:
                await self._conversations.save(
                    conversation.evolve(
                        workflow_id=WorkflowId(uuid4().hex), recovery_from=workflow_id
                    )
                )
                raise
            await self._conversations.save(
                conversation.evolve(
                    stage=WorkflowStage.CHOOSING_EPISODE,
                    episodes=episodes,
                    episode_offset=0,
                )
            )
            return SeasonSelectionOutcome(
                workflow_id, episodes, conversation.language or LanguageCode.ENGLISH
            )

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
            updated = conversation.evolve(selected_media=episode)
            try:
                page = await self._find_subtitles.find_for(updated)
            except ApplicationError:
                await self._conversations.save(
                    conversation.evolve(
                        workflow_id=WorkflowId(uuid4().hex), recovery_from=workflow_id
                    )
                )
                raise
            return EpisodeSelectionOutcome(workflow_id, episode, page)

    async def back_to_seasons(self, user_id: int, workflow_id: WorkflowId) -> NavigationOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_EPISODE
                or not isinstance(conversation.selected_media, SeriesRef)
            ):
                raise WorkflowExpiredError("Those seasons have expired. Search again.")
            updated = conversation.evolve(
                workflow_id=WorkflowId(uuid4().hex),
                stage=WorkflowStage.CHOOSING_SEASON,
                episodes=(),
                subtitle_candidates=(),
                subtitle_offset=0,
                recovery_from=None,
            )
            await self._conversations.save(updated)
            return self._outcome(updated)

    async def back_to_episodes(self, user_id: int, workflow_id: WorkflowId) -> NavigationOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            media = conversation.selected_media
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_SUBTITLE
                or not isinstance(media, EpisodeRef)
            ):
                raise WorkflowExpiredError("Those episodes have expired. Use the latest buttons.")
            episodes = conversation.episodes or tuple(
                await self._metadata.episodes(media.series, media.season_number)
            )
            updated = conversation.evolve(
                workflow_id=WorkflowId(uuid4().hex),
                stage=WorkflowStage.CHOOSING_EPISODE,
                selected_media=media.series,
                episodes=episodes,
                subtitle_candidates=(),
                subtitle_offset=0,
                recovery_from=None,
            )
            await self._conversations.save(updated)
            return self._outcome(updated)

    async def current_navigation(
        self, user_id: int, workflow_id: WorkflowId, *, rotate: bool = True, recover: bool = False
    ) -> NavigationOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if (
                conversation.workflow_id != workflow_id
                and not (recover and conversation.recovery_from == workflow_id)
            ) or conversation.stage not in {
                WorkflowStage.CHOOSING_SEASON,
                WorkflowStage.CHOOSING_EPISODE,
                WorkflowStage.CHOOSING_TITLE,
                WorkflowStage.CHOOSING_SUBTITLE,
                WorkflowStage.IDLE,
                WorkflowStage.AWAITING_TITLE,
            }:
                raise WorkflowExpiredError("These navigation buttons expired.")
            updated = (
                conversation.evolve(workflow_id=WorkflowId(uuid4().hex), recovery_from=None)
                if rotate
                else conversation
            )
            await self._conversations.save(updated)
            return self._outcome(updated)

    @staticmethod
    def _outcome(conversation: Conversation) -> NavigationOutcome:
        return NavigationOutcome(
            conversation.workflow_id,
            conversation.language or LanguageCode.ENGLISH,
            conversation.stage,
            conversation.seasons,
            conversation.episodes,
            conversation.search_results,
            {
                WorkflowStage.CHOOSING_TITLE: conversation.title_offset,
                WorkflowStage.CHOOSING_SEASON: conversation.season_offset,
                WorkflowStage.CHOOSING_EPISODE: conversation.episode_offset,
            }.get(conversation.stage, 0),
        )

    async def back_to_titles(self, user_id: int, workflow_id: WorkflowId) -> NavigationOutcome:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if (
                current.workflow_id != workflow_id
                or current.stage
                not in {WorkflowStage.CHOOSING_SEASON, WorkflowStage.CHOOSING_SUBTITLE}
                or not current.search_results
            ):
                raise WorkflowExpiredError("Those title results expired.")
            updated = current.evolve(
                workflow_id=WorkflowId(uuid4().hex),
                stage=WorkflowStage.CHOOSING_TITLE,
                selected_media=None,
                seasons=(),
                episodes=(),
                subtitle_candidates=(),
                recovery_from=None,
            )
            await self._conversations.save(updated)
            return self._outcome(updated)

    async def page_at(
        self, user_id: int, workflow_id: WorkflowId, stage: WorkflowStage, offset: int
    ) -> NavigationOutcome:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            mapping = {
                WorkflowStage.CHOOSING_TITLE: ("title_offset", current.search_results),
                WorkflowStage.CHOOSING_SEASON: ("season_offset", current.seasons),
                WorkflowStage.CHOOSING_EPISODE: ("episode_offset", current.episodes),
            }
            if (
                current.workflow_id != workflow_id
                or current.stage is not stage
                or stage not in mapping
                or offset < 0
                or offset % NAVIGATION_PAGE_SIZE
            ):
                raise WorkflowExpiredError("Those page buttons expired.")
            field, items = mapping[stage]
            if offset >= max(1, len(items)):
                raise WorkflowExpiredError("That page is unavailable.")
            updated = current.evolve(
                workflow_id=WorkflowId(uuid4().hex), recovery_from=None, **{field: offset}
            )
            await self._conversations.save(updated)
            return self._outcome(updated)
