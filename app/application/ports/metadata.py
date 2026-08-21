"""Movie and television metadata contract."""

from typing import Protocol

from app.domain.models import EpisodeRef, MediaSearchResult, SeasonSummary, SeriesRef


class MetadataGateway(Protocol):
    async def search(self, query: str) -> list[MediaSearchResult]: ...

    async def seasons(self, series: SeriesRef) -> list[SeasonSummary]: ...

    async def episodes(self, series: SeriesRef, season_number: int) -> list[EpisodeRef]: ...
