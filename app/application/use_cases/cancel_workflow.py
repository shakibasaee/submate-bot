"""Workflow cancellation."""

from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager


class CancelWorkflow:
    def __init__(self, conversations: ConversationRepository, locks: UserLockManager) -> None:
        self._conversations = conversations
        self._locks = locks

    async def execute(self, user_id: int) -> None:
        async with self._locks.hold(user_id):
            await self._conversations.reset_workflow(user_id)
