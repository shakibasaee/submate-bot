"""Validate and select one displayed movie or series."""

from app.application.dto import TitleSelectionOutcome, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.metadata import MetadataGateway
from app.application.use_cases.find_subtitles import FindSubtitles
from app.domain.errors import WorkflowExpiredError
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
                    search_results=(),
                )
                page = await self._find_subtitles.find_for(updated)
                return TitleSelectionOutcome(
                    workflow_id,
                    selected,
                    subtitle_page=page,
                )
            selected = SeriesRef(result.external_id, result.title, result.year)
            seasons = tuple(await self._metadata.seasons(selected))
            await self._conversations.save(
                conversation.evolve(
                    stage=WorkflowStage.CHOOSING_SEASON,
                    selected_media=selected,
                    search_results=(),
                    seasons=seasons,
                )
            )
            return TitleSelectionOutcome(workflow_id, selected, seasons=seasons)
