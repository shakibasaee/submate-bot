"""Safe subtitle validation and application delivery tests."""

import asyncio

import pytest

from app.domain.errors import UnsafeSubtitleError, WorkflowExpiredError
from app.domain.languages import LanguageCode
from app.domain.models import MediaSearchResult, MediaType
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
)
from app.infrastructure.providers.opensubtitles import MAX_SUBTITLE_BYTES, validate_srt
from tests.support import FakeMetadata, FakeProvider, build_test_application

VALID_SRT = b"1\r\n00:00:01,000 --> 00:00:03,500\r\nHello.\r\n"


def test_valid_srt_is_normalized_and_unsafe_files_are_rejected() -> None:
    assert validate_srt(VALID_SRT).startswith(b"1\n")
    for content in (b"", b"PK\x03\x04zip", b"binary\x00\x01", b"not a subtitle"):
        with pytest.raises(UnsafeSubtitleError):
            validate_srt(content)
    with pytest.raises(UnsafeSubtitleError, match="too large"):
        validate_srt(b"x" * (MAX_SUBTITLE_BYTES + 1))


def test_delivery_consumes_candidate_once_and_generates_safe_filename() -> None:
    candidate = SubtitleCandidate(
        ProviderId("fake"),
        ProviderFileRef("opaque"),
        LanguageCode.ENGLISH,
        "srt",
        "WEB-DL",
        attribution="Fake",
    )
    provider = FakeProvider(
        candidates=[candidate],
        downloaded=DownloadedSubtitle(VALID_SRT, "provider.srt", "srt", "Fake"),
    )
    metadata = FakeMetadata(
        search_results=[MediaSearchResult("1", MediaType.MOVIE, "Show: A/B?*", "2020")]
    )
    app = build_test_application(metadata=metadata, provider=provider)

    async def flow() -> None:
        await app.services.choose_language.execute(7, LanguageCode.ENGLISH)
        search = await app.services.search_titles.execute(7, "Show")
        await app.services.select_title.execute(7, search.workflow_id, MediaType.MOVIE, "1")
        delivered = await app.services.deliver_subtitle.execute(
            7, search.workflow_id, ProviderId("fake"), 0
        )
        assert delivered.subtitle.filename == "Show A B-en.srt"
        with pytest.raises(WorkflowExpiredError):
            await app.services.deliver_subtitle.execute(
                7, search.workflow_id, ProviderId("fake"), 0
            )

    asyncio.run(flow())
    assert provider.download_calls == 1
