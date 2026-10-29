"""Atomic candidate consumption and provider-neutral delivery."""

import re
from uuid import uuid4

from app.application.dto import (
    DeliveryAttempt,
    DeliveryOutcome,
    SubtitlePageOutcome,
    WorkflowStage,
    subtitle_page,
)
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.providers import SubtitleProvider
from app.application.ports.rate_limits import RateLimiter
from app.domain.errors import RateLimitedError, UnsafeSubtitleError, WorkflowExpiredError
from app.domain.models import EpisodeRef, MovieRef, WorkflowId
from app.domain.subtitles import DownloadedSubtitle, ProviderId


def _delivery_filename(media: MovieRef | EpisodeRef, language: str) -> str:
    title = media.title if isinstance(media, MovieRef) else media.series.title
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title)
    safe_title = re.sub(r"\s+", " ", safe_title).strip(" .")[:70] or "subtitle"
    episode = ""
    if isinstance(media, EpisodeRef):
        episode = f"-S{media.season_number:02d}E{media.episode_number:02d}"
    elif media.year and re.fullmatch(r"\d{4}", media.year):
        episode = f"-{media.year}"
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

    async def current_page(
        self, user_id: int, workflow_id: WorkflowId, *, rotate: bool = False
    ) -> SubtitlePageOutcome:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.workflow_id != workflow_id or current.stage not in {
                WorkflowStage.CHOOSING_SUBTITLE,
                WorkflowStage.CONFIRMING_DELIVERY,
            }:
                raise WorkflowExpiredError("These buttons expired. Send /start to search again.")
            assert current.language is not None
            if rotate:
                current = current.evolve(workflow_id=WorkflowId(uuid4().hex), recovery_from=None)
            offset = min(
                current.subtitle_offset, max(0, (len(current.subtitle_candidates) - 1) // 5 * 5)
            )
            current = current.evolve(subtitle_offset=offset)
            await self._conversations.save(current)
            return subtitle_page(current, offset)

    async def recovery_page(self, user_id: int, failed_workflow: WorkflowId) -> SubtitlePageOutcome:
        """Only the failed attempt may obtain its replacement recovery controls."""
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.stage not in {
                WorkflowStage.CHOOSING_SUBTITLE,
                WorkflowStage.CONFIRMING_DELIVERY,
            } or (
                current.workflow_id != failed_workflow and current.recovery_from != failed_workflow
            ):
                raise WorkflowExpiredError("These buttons expired. Use the latest message.")
            if current.workflow_id == failed_workflow:
                current = current.evolve(
                    workflow_id=WorkflowId(uuid4().hex), recovery_from=failed_workflow
                )
                await self._conversations.save(current)
            # No provider or metadata call is required to redisplay retained choices.
            return subtitle_page(current, current.subtitle_offset)

    async def finish(self, user_id: int, workflow_id: WorkflowId) -> WorkflowId:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.workflow_id != workflow_id or current.stage is not WorkflowStage.DELIVERING:
                raise WorkflowExpiredError("This delivery has expired.")
            updated = current.evolve(
                workflow_id=WorkflowId(uuid4().hex),
                stage=WorkflowStage.CHOOSING_SUBTITLE,
                recovery_from=None,
                download_started=False,
            )
            await self._conversations.save(updated)
            return updated.workflow_id

    async def restore(
        self,
        user_id: int,
        workflow_id: WorkflowId,
        *,
        uncertain: tuple[ProviderId, int] | None = None,
    ) -> None:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.workflow_id == workflow_id and current.stage is WorkflowStage.DELIVERING:
                await self._conversations.save(
                    current.evolve(
                        stage=WorkflowStage.CONFIRMING_DELIVERY
                        if uncertain is not None
                        else WorkflowStage.CHOOSING_SUBTITLE,
                        pending_delivery=uncertain,
                        workflow_id=WorkflowId(uuid4().hex),
                        recovery_from=workflow_id,
                        download_started=False,
                    )
                )

    async def acknowledge(self, user_id: int, workflow_id: WorkflowId) -> SubtitlePageOutcome:
        """Resolve uncertain receipt explicitly; never infer Telegram delivery from a timeout."""
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if (
                current.workflow_id != workflow_id
                or current.stage is not WorkflowStage.CONFIRMING_DELIVERY
                or current.pending_delivery is None
            ):
                raise WorkflowExpiredError("That delivery confirmation expired.")
            updated = current.evolve(
                workflow_id=WorkflowId(uuid4().hex),
                pending_delivery=None,
                stage=WorkflowStage.CHOOSING_SUBTITLE,
                recovery_from=None,
            )
            await self._conversations.save(updated)
            return subtitle_page(updated, updated.subtitle_offset)

    async def execute(
        self,
        user_id: int,
        workflow_id: WorkflowId,
        provider_id: ProviderId,
        candidate_index: int,
    ) -> DeliveryOutcome:
        attempt = await self.claim(user_id, workflow_id, provider_id, candidate_index)
        return await self.download(attempt)

    async def claim(
        self,
        user_id: int,
        workflow_id: WorkflowId,
        provider_id: ProviderId,
        candidate_index: int,
        *,
        confirm_resend: bool = False,
    ) -> DeliveryAttempt:
        async with self._locks.hold(user_id):
            conversation = await self._conversations.get(user_id)
            expected_stage = (
                WorkflowStage.CONFIRMING_DELIVERY
                if confirm_resend
                else WorkflowStage.CHOOSING_SUBTITLE
            )
            if (
                conversation.workflow_id != workflow_id
                or conversation.stage is not expected_stage
                or (
                    confirm_resend
                    and conversation.pending_delivery != (provider_id, candidate_index)
                )
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
            if confirm_resend:
                workflow_id = WorkflowId(uuid4().hex)
            await self._conversations.save(
                conversation.evolve(
                    workflow_id=workflow_id,
                    stage=WorkflowStage.DELIVERING,
                    download_started=False,
                    pending_delivery=None,
                )
            )

        return DeliveryAttempt(user_id, workflow_id, candidate, media, language)

    async def download(self, attempt: DeliveryAttempt) -> DeliveryOutcome:
        user_id, workflow_id = attempt.user_id, attempt.workflow_id
        candidate, media, language = attempt.candidate, attempt.media, attempt.language
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if (
                current.workflow_id != workflow_id
                or current.stage is not WorkflowStage.DELIVERING
                or current.download_started
            ):
                raise WorkflowExpiredError("That download attempt expired or already started.")
            await self._conversations.save(current.evolve(download_started=True))
        provider = self._providers.get(candidate.provider_id)
        if provider is None:
            await self.restore(user_id, workflow_id)
            raise WorkflowExpiredError("That subtitle provider is no longer available.")
        try:
            downloaded = await provider.download(candidate)
        except BaseException as error:
            async with self._locks.hold(user_id):
                current = await self._conversations.get(user_id)
                if current.workflow_id == workflow_id and current.stage is WorkflowStage.DELIVERING:
                    rejected = current.rejected_subtitles
                    candidates = current.subtitle_candidates
                    if isinstance(error, UnsafeSubtitleError):
                        identity = (candidate.provider_id, candidate.provider_file_ref)
                        rejected = rejected | {identity}
                        candidates = tuple(
                            item
                            for item in candidates
                            if (item.provider_id, item.provider_file_ref) not in rejected
                        )
                    await self._conversations.save(
                        current.evolve(
                            stage=WorkflowStage.CHOOSING_SUBTITLE,
                            workflow_id=WorkflowId(uuid4().hex),
                            recovery_from=workflow_id,
                            rejected_subtitles=rejected,
                            download_started=False,
                            subtitle_candidates=candidates,
                            subtitle_offset=min(
                                current.subtitle_offset, max(0, (len(candidates) - 1) // 5 * 5)
                            ),
                        )
                    )
            raise

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
