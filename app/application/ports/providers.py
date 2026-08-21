"""Provider-neutral subtitle contract."""

from typing import Protocol

from app.domain.subtitles import DownloadedSubtitle, ProviderId, SubtitleCandidate, SubtitleQuery


class SubtitleProvider(Protocol):
    @property
    def provider_id(self) -> ProviderId: ...

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]: ...

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle: ...
