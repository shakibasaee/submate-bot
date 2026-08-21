"""Regression tests for stale workflows, escaping, and concurrent delivery."""

import asyncio

import pytest

from app.application.dto import WorkflowStage
from app.bot.keyboards.media import result_label
from app.bot.keyboards.subtitles import subtitle_label
from app.bot.presentation import (
    TELEGRAM_BUTTON_TEXT_LIMIT,
    TELEGRAM_CAPTION_LIMIT,
    safe_caption,
    safe_html_text,
)
from app.domain.errors import WorkflowExpiredError
from app.domain.languages import LanguageCode
from app.domain.models import MediaSearchResult, MediaType
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
)
from app.infrastructure.persistence.memory import InMemoryConversationRepository
from tests.support import FakeMetadata, FakeProvider, build_test_application

VALID_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def test_html_and_long_external_labels_are_safe() -> None:
    assert safe_html_text("<b>Test</b> & broken <") == ("&lt;b&gt;Test&lt;/b&gt; &amp; broken &lt;")
    title = MediaSearchResult("1", MediaType.MOVIE, "<b>" + "x" * 200, "2025")
    candidate = SubtitleCandidate(
        ProviderId("fake"),
        ProviderFileRef("1"),
        LanguageCode.ENGLISH,
        "srt",
        "<i>" + "release" * 100,
        uploader="<b>bad</b>",
    )
    assert len(result_label(title)) <= TELEGRAM_BUTTON_TEXT_LIMIT
    assert len(subtitle_label(candidate)) <= TELEGRAM_BUTTON_TEXT_LIMIT
    caption = safe_caption("Uploader: <b>bad</b> " + "x" * 2000)
    assert len(caption) <= TELEGRAM_CAPTION_LIMIT
    assert "<b>" not in caption


def test_workflow_expiration_preserves_language_and_changes_identity() -> None:
    clock = {"now": 0.0}
    repository = InMemoryConversationRepository(
        ttl_seconds=10,
        clock=lambda: clock["now"],
    )

    async def scenario() -> None:
        initial = await repository.get(1)
        await repository.save(
            initial.evolve(
                stage=WorkflowStage.AWAITING_TITLE,
                language=LanguageCode.PERSIAN,
            )
        )
        clock["now"] = 11
        expired = await repository.get(1)
        assert expired.stage is WorkflowStage.IDLE
        assert expired.language is LanguageCode.PERSIAN
        assert expired.workflow_id != initial.workflow_id

    asyncio.run(scenario())


def test_cancelled_callback_identity_cannot_select_a_title() -> None:
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
    )
    app = build_test_application(metadata=metadata)

    async def scenario() -> None:
        await app.services.choose_language.execute(4, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(4, "Movie")
        await app.services.cancel_workflow.execute(4)
        with pytest.raises(WorkflowExpiredError):
            await app.services.select_title.execute(4, search.workflow_id, MediaType.MOVIE, "1")

    asyncio.run(scenario())


def test_rapid_duplicate_delivery_is_consumed_once() -> None:
    candidate = SubtitleCandidate(
        ProviderId("fake"),
        ProviderFileRef("same"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB-DL",
    )
    provider = FakeProvider(
        candidates=[candidate],
        downloaded=DownloadedSubtitle(VALID_SRT, "subtitle.srt", "srt", "Fake"),
    )
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("1", MediaType.MOVIE, "Movie", "2020")]
    )
    app = build_test_application(metadata=metadata, provider=provider)

    async def scenario() -> list[object]:
        await app.services.choose_language.execute(9, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(9, "Movie")
        await app.services.select_title.execute(9, search.workflow_id, MediaType.MOVIE, "1")
        return await asyncio.gather(
            app.services.deliver_subtitle.execute(9, search.workflow_id, ProviderId("fake"), 0),
            app.services.deliver_subtitle.execute(9, search.workflow_id, ProviderId("fake"), 0),
            return_exceptions=True,
        )

    results = asyncio.run(scenario())
    assert provider.download_calls == 1
    assert sum(isinstance(item, WorkflowExpiredError) for item in results) == 1
