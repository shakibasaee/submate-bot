"""Validated metadata title search."""

from app.application.dto import SearchTitlesOutcome, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.metadata import MetadataGateway
from app.application.ports.rate_limits import RateLimiter
from app.domain.errors import InvalidInputError, InvalidTransitionError, RateLimitedError


class SearchTitles:
    def __init__(
        self,
        conversations: ConversationRepository,
        metadata: MetadataGateway,
        rate_limiter: RateLimiter,
        locks: UserLockManager,
        *,
        user_limit: int = 10,
        global_limit: int = 120,
    ) -> None:
        self._conversations = conversations
        self._metadata = metadata
        self._rate_limiter = rate_limiter
        self._locks = locks
        self._user_limit = user_limit
        self._global_limit = global_limit

    async def execute(self, user_id: int, query: str) -> SearchTitlesOutcome:
        normalized = " ".join(query.split())
        if len(normalized) < 2:
            raise InvalidInputError("Please enter at least 2 characters for the title.")
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if conversation.language is None:
                raise InvalidTransitionError("Choose a subtitle language first with /language.")
            if conversation.stage is not WorkflowStage.AWAITING_TITLE:
                raise InvalidTransitionError("Use /language to start a subtitle search.")
            decision = await self._rate_limiter.check(
                "user-title-search", user_id, self._user_limit, 60
            )
            if not decision.allowed:
                raise RateLimitedError("Too many searches.", decision.retry_after)
            global_decision = await self._rate_limiter.check(
                "global-tmdb", "all", self._global_limit, 60
            )
            if not global_decision.allowed:
                raise RateLimitedError(
                    "Title search is busy right now.", global_decision.retry_after
                )
            results = tuple(await self._metadata.search(normalized))
            if results:
                await self._conversations.save(
                    conversation.evolve(
                        stage=WorkflowStage.CHOOSING_TITLE,
                        search_results=results,
                    )
                )
            return SearchTitlesOutcome(conversation.workflow_id, results)
