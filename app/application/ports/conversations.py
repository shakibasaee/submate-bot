"""Temporary workflow persistence contract."""

from typing import Protocol

from app.application.dto import Conversation


class ConversationRepository(Protocol):
    async def get(self, user_id: int) -> Conversation: ...

    async def save(self, conversation: Conversation) -> None: ...

    async def reset_workflow(self, user_id: int) -> Conversation: ...
