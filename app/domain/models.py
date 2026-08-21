"""Media references used across application boundaries."""

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

WorkflowId = NewType("WorkflowId", str)


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"


@dataclass(frozen=True, slots=True)
class MediaSearchResult:
    external_id: str
    media_type: MediaType
    title: str
    year: str | None = None


@dataclass(frozen=True, slots=True)
class MovieRef:
    external_id: str
    title: str
    year: str | None = None


@dataclass(frozen=True, slots=True)
class SeriesRef:
    external_id: str
    title: str
    year: str | None = None


@dataclass(frozen=True, slots=True)
class SeasonSummary:
    number: int
    name: str

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("season number must be positive")


@dataclass(frozen=True, slots=True)
class EpisodeRef:
    series: SeriesRef
    season_number: int
    episode_number: int
    name: str

    def __post_init__(self) -> None:
        if self.season_number < 1 or self.episode_number < 1:
            raise ValueError("season and episode numbers must be positive")
