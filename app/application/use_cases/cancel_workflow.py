"""Workflow cancellation."""

from app.application.dto import WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.domain.errors import WorkflowExpiredError
from app.domain.models import WorkflowId


class CancelWorkflow:
    def __init__(self, conversations: ConversationRepository, locks: UserLockManager) -> None:
        self._conversations = conversations
        self._locks = locks

    async def execute(self, user_id: int, expected_workflow: WorkflowId | None = None) -> None:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if expected_workflow is not None and (
                current.workflow_id != expected_workflow
                or current.stage is WorkflowStage.DELIVERING
            ):
                raise WorkflowExpiredError("These cancel buttons expired.")
            await self._conversations.reset_workflow(user_id)
