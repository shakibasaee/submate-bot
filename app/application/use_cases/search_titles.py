"""Validated metadata title search."""

import re
from difflib import SequenceMatcher

from app.application.dto import SearchTitlesOutcome, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.metadata import MetadataGateway
from app.application.ports.rate_limits import RateLimiter
from app.domain.errors import (
    InvalidInputError,
    InvalidTransitionError,
    MetadataError,
    RateLimitedError,
)


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
            if conversation.stage is WorkflowStage.DELIVERING:
                raise InvalidTransitionError("A subtitle is being delivered. Please wait a moment.")
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
            suggested = False
            if not results:
                prefix = _fallback_prefix(normalized)
                if (
                    prefix
                    and (
                        await self._rate_limiter.check("global-tmdb", "all", self._global_limit, 60)
                    ).allowed
                ):
                    try:
                        alternatives = await self._metadata.search(prefix)
                    except MetadataError:
                        alternatives = []
                    scores = [
                        (
                            SequenceMatcher(
                                None, _title_key(normalized), _title_key(item.title)
                            ).ratio(),
                            item,
                        )
                        for item in alternatives
                    ]
                    results = tuple(
                        item
                        for score, item in sorted(scores, key=lambda pair: pair[0], reverse=True)
                        if score >= 0.84
                    )
                    suggested = bool(results)
            # A new text search deliberately replaces prior selections and buttons.
            # Do this only after metadata succeeds, preserving choices on network failure.
            current = await self._conversations.reset_workflow(user_id)
            await self._conversations.save(
                current.evolve(
                    language=conversation.language,
                    stage=WorkflowStage.CHOOSING_TITLE if results else WorkflowStage.AWAITING_TITLE,
                    search_results=results,
                )
            )
            return SearchTitlesOutcome(
                current.workflow_id, results, conversation.language, suggested
            )


def _title_key(title: str) -> str:
    return " ".join(re.findall(r"\w+", title.casefold()))


def _fallback_prefix(title: str) -> str:
    words = _title_key(title).split()
    if not words:
        return ""
    index = max(range(len(words)), key=lambda i: len(words[i]))
    word = words[index]
    if len(word) < 6:
        return ""
    # Ask the metadata provider once for a prefix, then rank only actual titles.
    return " ".join([*words[:index], word[: max(4, len(word) // 2 + 1)]])
