"""Atomic candidate consumption and provider-neutral delivery."""

import re

from app.application.dto import DeliveryOutcome, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.providers import SubtitleProvider
from app.application.ports.rate_limits import RateLimiter
from app.domain.errors import RateLimitedError, WorkflowExpiredError
from app.domain.models import EpisodeRef, MovieRef, WorkflowId
from app.domain.subtitles import DownloadedSubtitle, ProviderId


def _delivery_filename(media: MovieRef | EpisodeRef, language: str) -> str:
    title = media.title if isinstance(media, MovieRef) else media.series.title
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title)
    safe_title = re.sub(r"\s+", " ", safe_title).strip(" .")[:70] or "subtitle"
    episode = ""
    if isinstance(media, EpisodeRef):
        episode = f"-S{media.season_number:02d}E{media.episode_number:02d}"
    return f"{safe_title}{episode}-{language}.srt"


class DeliverSubtitle:
    def __init__(
        self,
        conversations: ConversationRepository,
        providers: dict[ProviderId, SubtitleProvider],
        rate_limiter: RateLimiter,
        locks: UserLockManager,
        *,
        user_limit: int = 5,
        global_limit: int = 20,
    ) -> None:
        self._conversations = conversations
        self._providers = providers
        self._rate_limiter = rate_limiter
        self._locks = locks
        self._user_limit = user_limit
        self._global_limit = global_limit

    async def execute(
        self,
        user_id: int,
        workflow_id: WorkflowId,
        provider_id: ProviderId,
        candidate_index: int,
    ) -> DeliveryOutcome:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not WorkflowStage.CHOOSING_SUBTITLE
                or candidate_index < 0
                or candidate_index >= len(conversation.subtitle_candidates)
            ):
                raise WorkflowExpiredError("That subtitle result has expired. Search again.")
            candidate = conversation.subtitle_candidates[candidate_index]
            if candidate.provider_id != provider_id:
                raise WorkflowExpiredError("That subtitle result has expired. Search again.")
            decision = await self._rate_limiter.check(
                "user-subtitle-download", user_id, self._user_limit, 600
            )
            if not decision.allowed:
                raise RateLimitedError("Too many download attempts.", decision.retry_after)
            global_decision = await self._rate_limiter.check(
                "global-subtitle-download", "all", self._global_limit, 60
            )
            if not global_decision.allowed:
                raise RateLimitedError(
                    "Subtitle downloads are busy right now.",
                    global_decision.retry_after,
                )
            media = conversation.selected_media
            language = conversation.language
            if not isinstance(media, (MovieRef, EpisodeRef)) or language is None:
                raise WorkflowExpiredError("That subtitle selection has expired. Search again.")
            await self._conversations.save(
                conversation.evolve(
                    stage=WorkflowStage.DELIVERING,
                    subtitle_candidates=(),
                )
            )

        provider = self._providers.get(candidate.provider_id)
        if provider is None:
            raise WorkflowExpiredError("That subtitle provider is no longer available.")
        downloaded = await provider.download(candidate)

        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.workflow_id != workflow_id or current.stage is not WorkflowStage.DELIVERING:
                raise WorkflowExpiredError("That subtitle delivery was cancelled.")
            return DeliveryOutcome(
                DownloadedSubtitle(
                    content=downloaded.content,
                    filename=_delivery_filename(media, str(language)),
                    format=downloaded.format,
                    attribution=downloaded.attribution,
                    uploader=downloaded.uploader,
                )
            )
