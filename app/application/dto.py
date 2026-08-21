"""Immutable application state and structured workflow outcomes."""

from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain.languages import LanguageCode
from app.domain.models import (
    EpisodeRef,
    MediaSearchResult,
    MovieRef,
    SeasonSummary,
    SeriesRef,
    WorkflowId,
)
from app.domain.subtitles import DownloadedSubtitle, SubtitleCandidate


class WorkflowStage(StrEnum):
    IDLE = "idle"
    AWAITING_TITLE = "awaiting_title"
    CHOOSING_TITLE = "choosing_title"
    CHOOSING_SEASON = "choosing_season"
    CHOOSING_EPISODE = "choosing_episode"
    CHOOSING_SUBTITLE = "choosing_subtitle"
    DELIVERING = "delivering"


@dataclass(frozen=True, slots=True)
class Conversation:
    user_id: int
    workflow_id: WorkflowId
    stage: WorkflowStage = WorkflowStage.IDLE
    language: LanguageCode | None = None
    search_results: tuple[MediaSearchResult, ...] = ()
    selected_media: MovieRef | SeriesRef | EpisodeRef | None = None
    seasons: tuple[SeasonSummary, ...] = ()
    episodes: tuple[EpisodeRef, ...] = ()
    subtitle_candidates: tuple[SubtitleCandidate, ...] = ()
    subtitle_offset: int = 0

    def evolve(self, **changes: object) -> "Conversation":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class StartSearchOutcome:
    language: LanguageCode | None


@dataclass(frozen=True, slots=True)
class LanguageSelectedOutcome:
    workflow_id: WorkflowId
    language: LanguageCode


@dataclass(frozen=True, slots=True)
class SearchTitlesOutcome:
    workflow_id: WorkflowId
    results: tuple[MediaSearchResult, ...]


@dataclass(frozen=True, slots=True)
class TitleSelectionOutcome:
    workflow_id: WorkflowId
    selected: MovieRef | SeriesRef
    seasons: tuple[SeasonSummary, ...] = ()
    subtitle_page: "SubtitlePageOutcome | None" = None


@dataclass(frozen=True, slots=True)
class SeasonSelectionOutcome:
    workflow_id: WorkflowId
    episodes: tuple[EpisodeRef, ...]


@dataclass(frozen=True, slots=True)
class EpisodeSelectionOutcome:
    workflow_id: WorkflowId
    episode: EpisodeRef
    subtitle_page: "SubtitlePageOutcome"


@dataclass(frozen=True, slots=True)
class SubtitlePageOutcome:
    workflow_id: WorkflowId
    language: LanguageCode
    candidates: tuple[SubtitleCandidate, ...]
    offset: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    subtitle: DownloadedSubtitle


@dataclass(frozen=True, slots=True)
class ApplicationLimits:
    user_search: int = 10
    user_download: int = 5
    search_window_seconds: int = 60
    download_window_seconds: int = 600
    subtitle_page_size: int = 5
