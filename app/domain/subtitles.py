"""Normalized subtitle search and delivery models."""

from dataclasses import dataclass
from typing import NewType

from app.domain.languages import LanguageCode
from app.domain.models import EpisodeRef, MovieRef

ProviderId = NewType("ProviderId", str)
ProviderFileRef = NewType("ProviderFileRef", str)


@dataclass(frozen=True, slots=True)
class SubtitleQuery:
    media: MovieRef | EpisodeRef
    language: LanguageCode


@dataclass(frozen=True, slots=True)
class SubtitleCandidate:
    provider_id: ProviderId
    provider_file_ref: ProviderFileRef
    language: LanguageCode
    format: str
    release_name: str
    hearing_impaired: bool = False
    forced: bool = False
    rating: float | None = None
    download_count: int | None = None
    uploader: str | None = None
    attribution: str = ""

    @property
    def callback_key(self) -> str:
        return f"{self.provider_id}.{self.provider_file_ref}"


@dataclass(frozen=True, slots=True)
class DownloadedSubtitle:
    content: bytes
    filename: str
    format: str
    attribution: str
    uploader: str | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("downloaded subtitle cannot be empty")
