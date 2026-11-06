"""Build a bounded ZIP from a complete, provider-verified set of episode SRTs."""

import asyncio
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from app.application.dto import Conversation, WorkflowStage
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.providers import SeasonPackProvider
from app.application.ports.rate_limits import RateLimiter
from app.domain.errors import (
    ProviderNotFoundError,
    ProviderTimeoutError,
    RateLimitedError,
    UnsafeSubtitleError,
    WorkflowExpiredError,
)
from app.domain.models import SeriesRef, WorkflowId
from app.domain.subtitles import ProviderFileRef, ProviderId

MAX_PACK_EPISODES = 20
MAX_PACK_BYTES = 8 * 1024 * 1024


class SeasonPackUnavailable(ProviderNotFoundError):
    pass


class DownloadSeason:
    def __init__(
        self,
        conversations: ConversationRepository,
        provider: SeasonPackProvider,
        limiter: RateLimiter,
        locks: UserLockManager,
        global_limit: int,
    ) -> None:
        self._conversations = conversations
        self._provider = provider
        self._limiter = limiter
        self._locks = locks
        self.max_episodes = min(global_limit, MAX_PACK_EPISODES)
        self._global_limit = global_limit

    async def claim(self, user_id: int, workflow_id: WorkflowId) -> Conversation:
        async with self._locks.hold(user_id):
            state = await self._conversations.get(user_id)
            if (
                state.workflow_id != workflow_id
                or state.stage is not WorkflowStage.CHOOSING_EPISODE
                or not isinstance(state.selected_media, SeriesRef)
                or state.language is None
                or not state.episodes
                or len(state.episodes) > self.max_episodes
            ):
                raise WorkflowExpiredError("That season selection is no longer available.")
            decision = await self._limiter.check("user-season-pack", user_id, 2, 600)
            if not decision.allowed:
                raise RateLimitedError("Too many season pack attempts.", decision.retry_after)
            state = state.evolve(
                workflow_id=WorkflowId(uuid4().hex), stage=WorkflowStage.DELIVERING
            )
            await self._conversations.save(state)
            return state

    async def build(self, state: Conversation) -> bytes:
        assert isinstance(state.selected_media, SeriesRef) and state.language is not None
        season = state.episodes[0].season_number
        episodes = frozenset(item.episode_number for item in state.episodes)
        if (
            len(episodes) != len(state.episodes)
            or len(episodes) > self.max_episodes
            or any(
                item.season_number != season or item.series != state.selected_media
                for item in state.episodes
            )
        ):
            raise SeasonPackUnavailable("Episode coverage could not be confirmed.")
        try:
            async with asyncio.timeout(75):
                candidates = await self._provider.search_season(
                    state.selected_media, season, state.language, episodes
                )
                if candidates.keys() != episodes or any(
                    (item.provider_id, item.provider_file_ref) in state.rejected_subtitles
                    for item in candidates.values()
                ):
                    raise SeasonPackUnavailable("No complete pack is available.")
                contents = BytesIO()
                total = 0
                with ZipFile(contents, "w", ZIP_DEFLATED) as archive:
                    for episode in sorted(episodes):
                        decision = await self._limiter.check(
                            "global-subtitle-download", "all", self._global_limit, 60
                        )
                        if not decision.allowed:
                            raise RateLimitedError("Downloads are busy.", decision.retry_after)
                        candidate = candidates[episode]
                        try:
                            subtitle = await self._provider.download(candidate)
                        except UnsafeSubtitleError:
                            await self._reject(
                                state, candidate.provider_id, candidate.provider_file_ref
                            )
                            raise
                        total += len(subtitle.content)
                        if subtitle.format != "srt" or total > MAX_PACK_BYTES:
                            raise UnsafeSubtitleError("Season pack failed safety checks.")
                        archive.writestr(
                            f"S{season:02d}E{episode:02d}-{state.language}.srt", subtitle.content
                        )
                return contents.getvalue()
        except TimeoutError:
            raise ProviderTimeoutError("Season pack timed out.") from None

    async def _reject(
        self, state: Conversation, provider: ProviderId, file_ref: ProviderFileRef
    ) -> None:
        async with self._locks.hold(state.user_id):
            current = await self._conversations.get(state.user_id)
            if (
                current.workflow_id == state.workflow_id
                and current.stage is WorkflowStage.DELIVERING
            ):
                await self._conversations.save(
                    current.evolve(
                        rejected_subtitles=current.rejected_subtitles | {(provider, file_ref)}
                    )
                )

    async def finish(self, state: Conversation) -> WorkflowId:
        async with self._locks.hold(state.user_id):
            current = await self._conversations.get(state.user_id)
            if (
                current.workflow_id != state.workflow_id
                or current.stage is not WorkflowStage.DELIVERING
            ):
                raise WorkflowExpiredError("The season request expired.")
            workflow_id = WorkflowId(uuid4().hex)
            await self._conversations.save(
                current.evolve(workflow_id=workflow_id, stage=WorkflowStage.CHOOSING_EPISODE)
            )
            return workflow_id
