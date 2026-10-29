"""Start and language-selection workflows."""

from uuid import uuid4

from app.application.dto import (
    LanguageSelectedOutcome,
    StartSearchOutcome,
    WorkflowStage,
)
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.preferences import PreferenceRepository
from app.domain.errors import WorkflowExpiredError
from app.domain.languages import LanguageCode
from app.domain.models import WorkflowId


class StartSearch:
    def __init__(
        self,
        conversations: ConversationRepository,
        preferences: PreferenceRepository,
        locks: UserLockManager,
    ) -> None:
        self._conversations = conversations
        self._preferences = preferences
        self._locks = locks

    async def execute(
        self, user_id: int, expected_workflow: WorkflowId | None = None
    ) -> StartSearchOutcome:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.stage is WorkflowStage.DELIVERING:
                raise WorkflowExpiredError("A subtitle is being delivered. Please wait.")
            if expected_workflow is not None and (
                current.workflow_id != expected_workflow
                or current.stage is WorkflowStage.DELIVERING
            ):
                raise WorkflowExpiredError("These search buttons expired.")
            language = await self._preferences.get_language(user_id)
            conversation = await self._conversations.reset_workflow(user_id)
            if language is not None:
                await self._conversations.save(
                    conversation.evolve(language=language, stage=WorkflowStage.AWAITING_TITLE)
                )
        return StartSearchOutcome(language, conversation.workflow_id)


class ChooseLanguage:
    def __init__(
        self,
        conversations: ConversationRepository,
        preferences: PreferenceRepository,
        locks: UserLockManager,
    ) -> None:
        self._conversations = conversations
        self._preferences = preferences
        self._locks = locks

    async def open_picker(
        self, user_id: int, expected_workflow: WorkflowId | None = None
    ) -> LanguageSelectedOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if expected_workflow is not None and conversation.workflow_id != expected_workflow:
                raise WorkflowExpiredError("That language button expired.")
            if conversation.stage in {WorkflowStage.DELIVERING, WorkflowStage.CONFIRMING_DELIVERY}:
                raise WorkflowExpiredError("A subtitle is being delivered. Please wait.")
            if conversation.stage not in {
                WorkflowStage.CHOOSING_SUBTITLE,
                WorkflowStage.CHOOSING_EPISODE,
                WorkflowStage.CHOOSING_SEASON,
                WorkflowStage.CHOOSING_TITLE,
            }:
                conversation = await self._conversations.reset_workflow(user_id)
            updated = conversation.evolve(workflow_id=WorkflowId(uuid4().hex), recovery_from=None)
            await self._conversations.save(updated)
            return LanguageSelectedOutcome(
                updated.workflow_id, updated.language or LanguageCode.ENGLISH, updated.stage
            )

    async def execute(
        self, user_id: int, language: LanguageCode, expected_workflow: WorkflowId | None = None
    ) -> LanguageSelectedOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if conversation.stage in {WorkflowStage.DELIVERING, WorkflowStage.CONFIRMING_DELIVERY}:
                raise WorkflowExpiredError("Resolve the current delivery before changing language.")
            if expected_workflow is not None and (
                conversation.workflow_id != expected_workflow
                or conversation.stage
                not in {
                    WorkflowStage.CHOOSING_SUBTITLE,
                    WorkflowStage.CHOOSING_SEASON,
                    WorkflowStage.CHOOSING_EPISODE,
                    WorkflowStage.IDLE,
                    WorkflowStage.AWAITING_TITLE,
                    WorkflowStage.CHOOSING_TITLE,
                }
            ):
                raise WorkflowExpiredError("That language picker expired. Use /language.")
            await self._preferences.set_language(user_id, language)
            workflow_id = WorkflowId(uuid4().hex)
            if expected_workflow is not None and conversation.stage in {
                WorkflowStage.CHOOSING_SUBTITLE,
                WorkflowStage.CHOOSING_EPISODE,
                WorkflowStage.CHOOSING_SEASON,
                WorkflowStage.CHOOSING_TITLE,
            }:
                await self._conversations.save(
                    conversation.evolve(
                        workflow_id=workflow_id,
                        language=language,
                        subtitle_candidates=(),
                        subtitle_offset=0,
                        recovery_from=None,
                    )
                )
                return LanguageSelectedOutcome(
                    workflow_id,
                    language,
                    conversation.stage,
                    conversation.seasons,
                    conversation.episodes,
                )
            await self._conversations.save(
                conversation.evolve(
                    workflow_id=workflow_id,
                    stage=WorkflowStage.AWAITING_TITLE,
                    language=language,
                    search_results=(),
                    selected_media=None,
                    seasons=(),
                    episodes=(),
                    subtitle_candidates=(),
                    subtitle_offset=0,
                    rejected_subtitles=frozenset(),
                    recovery_from=None,
                )
            )
        return LanguageSelectedOutcome(workflow_id, language)
