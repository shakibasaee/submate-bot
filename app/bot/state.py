"""In-memory conversation state scoped to individual Telegram users."""

from dataclasses import dataclass
from enum import StrEnum


class SubtitleLanguage(StrEnum):
    """Subtitle languages supported by the first search flow."""

    ENGLISH = "en"
    PERSIAN = "fa"


class MediaType(StrEnum):
    """TMDb media types that can have subtitles."""

    MOVIE = "movie"
    TV = "tv"


@dataclass(frozen=True)
class SearchResult:
    """A safe, display-ready subset of a TMDb search result."""

    tmdb_id: int
    media_type: MediaType
    title: str
    year: str | None


@dataclass(frozen=True)
class Season:
    """A selectable non-special TV season."""

    number: int
    name: str


@dataclass(frozen=True)
class Episode:
    """A selectable episode within a TV season."""

    number: int
    name: str


@dataclass(frozen=True)
class SubtitleResult:
    """A selectable subtitle file returned by an approved provider."""

    file_id: int
    release: str
    format: str
    hearing_impaired: bool
    download_count: int | None
    rating: float | None
    uploader: str | None


@dataclass
class UserConversation:
    """The small amount of state needed before subtitle searching begins."""

    language: SubtitleLanguage | None = None
    awaiting_title: bool = False
    selected_tmdb_id: int | None = None
    selected_media_type: MediaType | None = None
    search_results: dict[tuple[MediaType, int], SearchResult] | None = None
    seasons: dict[int, Season] | None = None
    episodes: dict[int, Episode] | None = None
    selected_season_number: int | None = None
    selected_episode_number: int | None = None
    selected_title: str | None = None
    subtitle_results: dict[int, SubtitleResult] | None = None
    subtitle_offset: int = 0
    selected_subtitle_file_id: int | None = None


class ConversationStore:
    """Keep conversation data isolated by Telegram user ID."""

    def __init__(self) -> None:
        self._conversations: dict[int, UserConversation] = {}

    def get(self, user_id: int) -> UserConversation:
        """Return a user's conversation, creating it when needed."""
        return self._conversations.setdefault(user_id, UserConversation())

    def choose_language(self, user_id: int, language: SubtitleLanguage) -> None:
        """Save a language choice and move the user to title entry."""
        conversation = self.get(user_id)
        conversation.language = language
        conversation.awaiting_title = True
        conversation.selected_tmdb_id = None
        conversation.selected_media_type = None
        conversation.search_results = None
        conversation.seasons = None
        conversation.episodes = None
        conversation.selected_season_number = None
        conversation.selected_episode_number = None
        conversation.selected_title = None
        conversation.subtitle_results = None
        conversation.subtitle_offset = 0
        conversation.selected_subtitle_file_id = None

    def restore_language(self, user_id: int, language: SubtitleLanguage) -> None:
        """Restore a durable preference without starting a new search action."""
        self.get(user_id).language = language

    def cancel(self, user_id: int) -> None:
        """End the active action while retaining the user's language choice."""
        conversation = self.get(user_id)
        conversation.awaiting_title = False
        conversation.search_results = None
        conversation.seasons = None
        conversation.episodes = None

    def set_search_results(self, user_id: int, results: list[SearchResult]) -> None:
        """Store only the choices shown to this user for callback validation."""
        conversation = self.get(user_id)
        conversation.search_results = {
            (result.media_type, result.tmdb_id): result for result in results
        }

    def select_result(
        self, user_id: int, media_type: MediaType, tmdb_id: int
    ) -> SearchResult | None:
        """Select a result only if it appeared in this user's latest search."""
        conversation = self.get(user_id)
        result = (conversation.search_results or {}).get((media_type, tmdb_id))
        if result is None:
            return None
        conversation.selected_tmdb_id = tmdb_id
        conversation.selected_media_type = media_type
        conversation.selected_title = result.title
        conversation.awaiting_title = False
        conversation.search_results = None
        return result

    def set_seasons(self, user_id: int, seasons: list[Season]) -> None:
        """Save the selectable seasons returned for the chosen series."""
        conversation = self.get(user_id)
        conversation.seasons = {season.number: season for season in seasons}
        conversation.episodes = None
        conversation.selected_season_number = None
        conversation.selected_episode_number = None

    def select_season(self, user_id: int, number: int) -> Season | None:
        """Select a displayed season and reject forged or expired choices."""
        season = (self.get(user_id).seasons or {}).get(number)
        if season is not None:
            self.get(user_id).selected_season_number = number
        return season

    def set_episodes(self, user_id: int, episodes: list[Episode]) -> None:
        """Save the selectable episodes from the selected season."""
        self.get(user_id).episodes = {episode.number: episode for episode in episodes}

    def select_episode(
        self, user_id: int, season_number: int, episode_number: int
    ) -> Episode | None:
        """Save an episode only when it belongs to the active selected season."""
        conversation = self.get(user_id)
        if conversation.selected_season_number != season_number:
            return None
        episode = (conversation.episodes or {}).get(episode_number)
        if episode is not None:
            conversation.selected_episode_number = episode_number
            conversation.awaiting_title = False
            conversation.episodes = None
        return episode

    def set_subtitle_results(self, user_id: int, results: list[SubtitleResult]) -> None:
        """Save provider results so only displayed files can be selected."""
        conversation = self.get(user_id)
        conversation.subtitle_results = {result.file_id: result for result in results}
        conversation.subtitle_offset = 0

    def select_subtitle(self, user_id: int, file_id: int) -> SubtitleResult | None:
        """Store a selected provider file only when it was in the latest results."""
        result = (self.get(user_id).subtitle_results or {}).get(file_id)
        if result is not None:
            self.get(user_id).selected_subtitle_file_id = file_id
        return result

    def back_to_seasons(self, user_id: int) -> bool:
        """Discard an episode view and return to the latest valid season list."""
        conversation = self.get(user_id)
        if not conversation.seasons:
            return False
        conversation.episodes = None
        conversation.selected_season_number = None
        return True


conversation_store = ConversationStore()
