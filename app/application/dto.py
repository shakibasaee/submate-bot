"""Immutable application state and structured workflow outcomes."""

from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain.languages import InterfaceLanguage, LanguageCode
from app.domain.models import (
    EpisodeRef,
    MediaSearchResult,
    MovieRef,
    SeasonSummary,
    SeriesRef,
    WorkflowId,
)
from app.domain.subtitles import DownloadedSubtitle, ProviderFileRef, ProviderId, SubtitleCandidate


class WorkflowStage(StrEnum):
    IDLE = "idle"
    AWAITING_TITLE = "awaiting_title"
    CHOOSING_TITLE = "choosing_title"
    CHOOSING_SEASON = "choosing_season"
    CHOOSING_EPISODE = "choosing_episode"
    CHOOSING_SUBTITLE = "choosing_subtitle"
    DELIVERING = "delivering"
    CONFIRMING_DELIVERY = "confirming_delivery"


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
    rejected_subtitles: frozenset[tuple[ProviderId, ProviderFileRef]] = frozenset()
    recovery_from: WorkflowId | None = None
    title_offset: int = 0
    season_offset: int = 0
    episode_offset: int = 0
    download_started: bool = False
    interface_picker_id: str | None = None
    pending_delivery: tuple[ProviderId, int] | None = None

    def evolve(self, **changes: object) -> "Conversation":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class InterfaceChoiceOutcome:
    language: InterfaceLanguage | None
    subtitle_language: LanguageCode | None
    picker_id: str | None = None


@dataclass(frozen=True, slots=True)
class StartSearchOutcome:
    language: LanguageCode | None
    workflow_id: WorkflowId | None = None


@dataclass(frozen=True, slots=True)
class LanguageSelectedOutcome:
    workflow_id: WorkflowId
    language: LanguageCode
    stage: WorkflowStage = WorkflowStage.AWAITING_TITLE
    seasons: tuple[SeasonSummary, ...] = ()
    episodes: tuple[EpisodeRef, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchTitlesOutcome:
    workflow_id: WorkflowId
    results: tuple[MediaSearchResult, ...]
    language: LanguageCode = LanguageCode.ENGLISH


@dataclass(frozen=True, slots=True)
class TitleSelectionOutcome:
    workflow_id: WorkflowId
    selected: MovieRef | SeriesRef
    seasons: tuple[SeasonSummary, ...] = ()
    subtitle_page: "SubtitlePageOutcome | None" = None
    language: LanguageCode = LanguageCode.ENGLISH


@dataclass(frozen=True, slots=True)
class SeasonSelectionOutcome:
    workflow_id: WorkflowId
    episodes: tuple[EpisodeRef, ...]
    language: LanguageCode = LanguageCode.ENGLISH


@dataclass(frozen=True, slots=True)
class NavigationOutcome:
    workflow_id: WorkflowId
    language: LanguageCode
    stage: WorkflowStage
    seasons: tuple[SeasonSummary, ...] = ()
    episodes: tuple[EpisodeRef, ...] = ()
    results: tuple[MediaSearchResult, ...] = ()
    offset: int = 0


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
    is_episode: bool = False
    title: str = "this title"
    total: int = 0
    pending_delivery: tuple[ProviderId, int] | None = None


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    subtitle: DownloadedSubtitle


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    user_id: int
    workflow_id: WorkflowId
    candidate: SubtitleCandidate
    media: MovieRef | EpisodeRef
    language: LanguageCode


@dataclass(frozen=True, slots=True)
class ApplicationLimits:
    user_search: int = 10
    user_download: int = 5
    search_window_seconds: int = 60
    download_window_seconds: int = 600
    subtitle_page_size: int = 5


def subtitle_page(
    conversation: Conversation, offset: int = 0, size: int = 5
) -> SubtitlePageOutcome:
    assert conversation.language is not None
    media = conversation.selected_media
    return SubtitlePageOutcome(
        conversation.workflow_id,
        conversation.language,
        conversation.subtitle_candidates[offset : offset + size],
        offset,
        offset + size < len(conversation.subtitle_candidates),
        isinstance(media, EpisodeRef),
        f"{media.series.title} · S{media.season_number:02d}E{media.episode_number:02d}"
        if isinstance(media, EpisodeRef)
        else getattr(media, "title", "this title"),
        len(conversation.subtitle_candidates),
        conversation.pending_delivery,
    )
