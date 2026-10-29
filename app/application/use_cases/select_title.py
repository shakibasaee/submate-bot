"""Validate and select one displayed movie or series."""

from uuid import uuid4

from app.application.dto import TitleSelectionOutcome, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.metadata import MetadataGateway
from app.application.use_cases.find_subtitles import FindSubtitles
from app.domain.errors import ApplicationError, WorkflowExpiredError
from app.domain.languages import LanguageCode
from app.domain.models import MediaType, MovieRef, SeriesRef, WorkflowId


class SelectTitle:
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

    async def execute(
        self, user_id: int, workflow_id: WorkflowId, media_type: MediaType, external_id: str
    ) -> TitleSelectionOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_TITLE
            ):
                raise WorkflowExpiredError("That result has expired. Search again.")
            result = next(
                (
                    item
                    for item in conversation.search_results
                    if item.media_type is media_type and item.external_id == external_id
                ),
                None,
            )
            if result is None:
                raise WorkflowExpiredError("That result has expired. Search again.")
            if media_type is MediaType.MOVIE:
                selected = MovieRef(result.external_id, result.title, result.year)
                updated = conversation.evolve(
                    selected_media=selected,
                    season_offset=0,
                    episode_offset=0,
                )
                try:
                    page = await self._find_subtitles.find_for(updated)
                except ApplicationError:
                    await self._conversations.save(
                        conversation.evolve(
                            workflow_id=WorkflowId(uuid4().hex), recovery_from=workflow_id
                        )
                    )
                    raise
                return TitleSelectionOutcome(
                    workflow_id,
                    selected,
                    subtitle_page=page,
                )
            selected = SeriesRef(result.external_id, result.title, result.year)
            try:
                seasons = tuple(await self._metadata.seasons(selected))
            except ApplicationError:
                await self._conversations.save(
                    conversation.evolve(
                        workflow_id=WorkflowId(uuid4().hex), recovery_from=workflow_id
                    )
                )
                raise
            await self._conversations.save(
                conversation.evolve(
                    stage=WorkflowStage.CHOOSING_SEASON,
                    selected_media=selected,
                    seasons=seasons,
                    season_offset=0,
                    episode_offset=0,
                )
            )
            return TitleSelectionOutcome(
                workflow_id,
                selected,
                seasons=seasons,
                language=conversation.language or LanguageCode.ENGLISH,
            )
