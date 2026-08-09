"""State-level coverage of the complete user selection and delivery handoff flow."""

from app.bot.state import (
    ConversationStore,
    Episode,
    MediaType,
    SearchResult,
    Season,
    SubtitleLanguage,
    SubtitleResult,
)


def test_tv_user_flow_reaches_exact_subtitle_file_selection() -> None:
    store = ConversationStore()
    user_id = 77
    title = SearchResult(1396, MediaType.TV, "Example Series", "2008")
    subtitle = SubtitleResult(9001, "WEB-DL", "srt", False, 120, 9.0, "uploader")

    store.choose_language(user_id, SubtitleLanguage.ENGLISH)
    workflow_id = store.get(user_id).workflow_id
    store.set_search_results(user_id, workflow_id, [title])
    assert store.select_result(user_id, workflow_id, MediaType.TV, 1396) == title
    store.set_seasons(user_id, workflow_id, [Season(2, "Season 2")])
    assert store.select_season(user_id, workflow_id, 2) == Season(2, "Season 2")
    store.set_episodes(user_id, workflow_id, [Episode(5, "Episode Five")])
    assert store.select_episode(user_id, workflow_id, 2, 5) == Episode(5, "Episode Five")
    store.set_subtitle_results(user_id, workflow_id, [subtitle])
    assert store.select_subtitle(user_id, workflow_id, 9001) == subtitle

    conversation = store.get(user_id)
    assert conversation.language is SubtitleLanguage.ENGLISH
    assert conversation.selected_tmdb_id == 1396
    assert conversation.selected_season_number == 2
    assert conversation.selected_episode_number == 5
    assert conversation.selected_subtitle_file_id == 9001
