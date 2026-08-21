"""Provider-neutral fakes and application factory used by tests."""

from dataclasses import dataclass, field

from app.application.container import ApplicationServices
from app.application.use_cases import (
    CancelWorkflow,
    ChooseLanguage,
    DeliverSubtitle,
    FindSubtitles,
    NavigateSeries,
    SearchTitles,
    SelectTitle,
    StartSearch,
)
from app.domain.models import EpisodeRef, MediaSearchResult, SeasonSummary, SeriesRef
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderId,
    SubtitleCandidate,
    SubtitleQuery,
)
from app.infrastructure.cache.memory import InMemoryRateLimiter
from app.infrastructure.persistence.memory import (
    InMemoryConversationRepository,
    InMemoryPreferenceRepository,
    InMemoryUserLockManager,
)


@dataclass
class FakeMetadata:
    search_results: list[MediaSearchResult] = field(default_factory=list)
    season_results: list[SeasonSummary] = field(default_factory=list)
    episode_results: list[EpisodeRef] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    async def search(self, query: str) -> list[MediaSearchResult]:
        self.queries.append(query)
        return self.search_results

    async def seasons(self, series: SeriesRef) -> list[SeasonSummary]:
        return self.season_results

    async def episodes(self, series: SeriesRef, season_number: int) -> list[EpisodeRef]:
        return [item for item in self.episode_results if item.season_number == season_number]


@dataclass
class FakeProvider:
    candidates: list[SubtitleCandidate] = field(default_factory=list)
    downloaded: DownloadedSubtitle | None = None
    search_queries: list[SubtitleQuery] = field(default_factory=list)
    download_calls: int = 0
    provider_id: ProviderId = ProviderId("fake")

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]:
        self.search_queries.append(query)
        return self.candidates

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle:
        self.download_calls += 1
        if self.downloaded is None:
            raise AssertionError("fake download was not configured")
        return self.downloaded


@dataclass
class TestApplication:
    services: ApplicationServices
    conversations: InMemoryConversationRepository
    preferences: InMemoryPreferenceRepository
    locks: InMemoryUserLockManager
    metadata: FakeMetadata
    provider: FakeProvider


def build_test_application(
    *,
    metadata: FakeMetadata | None = None,
    provider: FakeProvider | None = None,
    conversation_ttl: int = 1800,
) -> TestApplication:
    conversations = InMemoryConversationRepository(ttl_seconds=conversation_ttl)
    preferences = InMemoryPreferenceRepository()
    locks = InMemoryUserLockManager()
    limiter = InMemoryRateLimiter()
    metadata = metadata or FakeMetadata()
    provider = provider or FakeProvider()
    find = FindSubtitles(conversations, (provider,), limiter, locks)
    services = ApplicationServices(
        start_search=StartSearch(conversations, preferences, locks),
        choose_language=ChooseLanguage(conversations, preferences, locks),
        search_titles=SearchTitles(conversations, metadata, limiter, locks),
        select_title=SelectTitle(conversations, metadata, find, locks),
        navigate_series=NavigateSeries(conversations, metadata, find, locks),
        find_subtitles=find,
        deliver_subtitle=DeliverSubtitle(
            conversations,
            {provider.provider_id: provider},
            limiter,
            locks,
        ),
        cancel_workflow=CancelWorkflow(conversations, locks),
    )
    return TestApplication(services, conversations, preferences, locks, metadata, provider)
