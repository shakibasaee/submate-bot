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

    async def execute(self, user_id: int) -> StartSearchOutcome:
        language = await self._preferences.get_language(user_id)
        async with self._locks.hold(user_id):
            conversation = await self._conversations.reset_workflow(user_id)
            if language is not None:
                await self._conversations.save(
                    conversation.evolve(language=language, stage=WorkflowStage.AWAITING_TITLE)
                )
        return StartSearchOutcome(language)


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

    async def execute(
        self, user_id: int, language: LanguageCode, expected_workflow: WorkflowId | None = None
    ) -> LanguageSelectedOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if expected_workflow is not None and (
                conversation.workflow_id != expected_workflow
                or conversation.stage is not WorkflowStage.CHOOSING_SUBTITLE
            ):
                raise WorkflowExpiredError("That language picker expired. Use /language.")
            await self._preferences.set_language(user_id, language)
            workflow_id = WorkflowId(uuid4().hex)
            if expected_workflow is not None:
                await self._conversations.save(
                    conversation.evolve(
                        workflow_id=workflow_id,
                        language=language,
                        subtitle_candidates=(),
                        subtitle_offset=0,
                    )
                )
                return LanguageSelectedOutcome(workflow_id, language)
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
                )
            )
        return LanguageSelectedOutcome(workflow_id, language)
