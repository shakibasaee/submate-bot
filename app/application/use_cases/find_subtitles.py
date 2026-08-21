"""Provider-neutral subtitle discovery and deterministic ranking."""

from app.application.dto import Conversation, SubtitlePageOutcome, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.providers import SubtitleProvider
from app.application.ports.rate_limits import RateLimiter
from app.domain.errors import InvalidTransitionError, RateLimitedError
from app.domain.models import EpisodeRef, MovieRef, WorkflowId
from app.domain.subtitles import SubtitleCandidate, SubtitleQuery


def rank_candidates(candidates: list[SubtitleCandidate]) -> list[SubtitleCandidate]:
    return sorted(
        candidates,
        key=lambda item: (
            item.format.casefold() != "srt",
            -item.rating if item.rating is not None else 0,
            -item.download_count if item.download_count is not None else 0,
            item.provider_id,
            item.provider_file_ref,
        ),
    )


class FindSubtitles:
    def __init__(
        self,
        conversations: ConversationRepository,
        providers: tuple[SubtitleProvider, ...],
        rate_limiter: RateLimiter,
        locks: UserLockManager,
        *,
        page_size: int = 5,
        user_limit: int = 10,
        global_limit: int = 60,
    ) -> None:
        self._conversations = conversations
        self._providers = providers
        self._rate_limiter = rate_limiter
        self._locks = locks
        self._page_size = page_size
        self._user_limit = user_limit
        self._global_limit = global_limit

    async def find_for(self, conversation: Conversation) -> SubtitlePageOutcome:
        media = conversation.selected_media
        if conversation.language is None or not isinstance(media, (MovieRef, EpisodeRef)):
            raise InvalidTransitionError("The selected movie or episode is incomplete.")
        decision = await self._rate_limiter.check(
            "user-subtitle-search", conversation.user_id, self._user_limit, 60
        )
        if not decision.allowed:
            raise RateLimitedError("Too many subtitle searches.", decision.retry_after)
        global_decision = await self._rate_limiter.check(
            "global-subtitle-search", "all", self._global_limit, 60
        )
        if not global_decision.allowed:
            raise RateLimitedError(
                "Subtitle search is busy right now.", global_decision.retry_after
            )
        query = SubtitleQuery(media=media, language=conversation.language)
        candidates: list[SubtitleCandidate] = []
        for provider in self._providers:
            candidates.extend(await provider.search(query))
        ranked = tuple(rank_candidates(candidates))
        updated = conversation.evolve(
            stage=WorkflowStage.CHOOSING_SUBTITLE,
            subtitle_candidates=ranked,
            subtitle_offset=0,
        )
        await self._conversations.save(updated)
        return self.page(updated, 0)

    def page(self, conversation: Conversation, offset: int) -> SubtitlePageOutcome:
        if conversation.language is None:
            raise InvalidTransitionError("Choose a subtitle language first.")
        candidates = conversation.subtitle_candidates[offset : offset + self._page_size]
        return SubtitlePageOutcome(
            workflow_id=conversation.workflow_id,
            language=conversation.language,
            candidates=candidates,
            offset=offset,
            has_more=offset + self._page_size < len(conversation.subtitle_candidates),
        )

    async def next_page(self, user_id: int, workflow_id: WorkflowId) -> SubtitlePageOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_SUBTITLE
            ):
                raise InvalidTransitionError("Those subtitle results have expired.")
            offset = conversation.subtitle_offset + self._page_size
            page = self.page(conversation, offset)
            if not page.candidates:
                raise InvalidTransitionError("No more results.")
            await self._conversations.save(conversation.evolve(subtitle_offset=offset))
            return page
