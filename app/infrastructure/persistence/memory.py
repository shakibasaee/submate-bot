"""Single-process repositories and per-user locks."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from app.application.dto import Conversation, WorkflowStage
from app.domain.languages import LanguageCode
from app.domain.models import WorkflowId


class InMemoryConversationRepository:
    """Temporary conversation storage with lazy workflow expiration."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 30 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._conversations: dict[int, tuple[Conversation, float]] = {}

    def _empty(self, user_id: int, language: LanguageCode | None = None) -> Conversation:
        return Conversation(
            user_id=user_id,
            workflow_id=WorkflowId(uuid4().hex),
            language=language,
        )

    async def get(self, user_id: int) -> Conversation:
        saved = self._conversations.get(user_id)
        if saved is None:
            conversation = self._empty(user_id)
            self._conversations[user_id] = (conversation, self._clock())
            return conversation
        conversation, touched_at = saved
        if (
            conversation.stage is not WorkflowStage.IDLE
            and self._clock() - touched_at >= self._ttl_seconds
        ):
            conversation = self._empty(user_id, conversation.language)
            self._conversations[user_id] = (conversation, self._clock())
        return conversation

    async def save(self, conversation: Conversation) -> None:
        self._conversations[conversation.user_id] = (conversation, self._clock())

    async def reset_workflow(self, user_id: int) -> Conversation:
        current = await self.get(user_id)
        reset = self._empty(user_id, current.language)
        await self.save(reset)
        return reset


class InMemoryPreferenceRepository:
    def __init__(self) -> None:
        self._languages: dict[int, LanguageCode] = {}

    async def get_language(self, user_id: int) -> LanguageCode | None:
        return self._languages.get(user_id)

    async def set_language(self, user_id: int, language: LanguageCode) -> None:
        self._languages[user_id] = language

    async def close(self) -> None:
        return None


class InMemoryUserLockManager:
    """Serialize state-changing operations independently for each user."""

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, user_id: int) -> AsyncIterator[None]:
        async with self._registry_lock:
            lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            yield
