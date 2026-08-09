"""Tests for safe subtitle validation and temporary-file handling."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from app.bot.handlers import subtitle as subtitle_handler
from app.bot.handlers.subtitle import deliver_subtitle, delivery_filename, temporary_srt
from app.bot.state import SubtitleLanguage, SubtitleResult, conversation_store
from app.services.opensubtitles import (
    MAX_SUBTITLE_BYTES,
    DownloadLink,
    UnsafeSubtitleError,
    validate_srt,
)

VALID_SRT = b"1\r\n00:00:01,000 --> 00:00:03,500\r\nHello from a subtitle.\r\n"


def test_valid_srt_is_normalized_to_utf8_lf() -> None:
    assert validate_srt(VALID_SRT) == (
        b"1\n00:00:01,000 --> 00:00:03,500\nHello from a subtitle.\n"
    )


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"PK\x03\x04fake zip",
        b"Rar!fake archive",
        b"not a subtitle",
        b"\x00\x01\x02\x03binary",
    ],
)
def test_unsafe_archive_empty_binary_and_corrupt_files_are_rejected(content: bytes) -> None:
    with pytest.raises(UnsafeSubtitleError):
        validate_srt(content)


def test_oversized_subtitle_is_rejected() -> None:
    with pytest.raises(UnsafeSubtitleError, match="too large"):
        validate_srt(b"x" * (MAX_SUBTITLE_BYTES + 1))


def test_temporary_srt_is_deleted_after_success() -> None:
    path: Path
    with temporary_srt(VALID_SRT) as path:
        assert path.exists()
        assert path.read_bytes() == VALID_SRT
    assert not path.exists()


def test_temporary_srt_is_deleted_after_failure() -> None:
    path: Path
    with pytest.raises(RuntimeError, match="send failed"), temporary_srt(VALID_SRT) as path:
        raise RuntimeError("send failed")
    assert not path.exists()


def test_delivery_filename_is_clear_and_sanitized() -> None:
    assert delivery_filename("Show: A/B?*", "fa", 2, 3) == "Show A B-S02E03-fa.srt"


def test_valid_srt_is_sent_then_immediately_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOpenSubtitlesClient:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-api-key"

        async def request_download_link(self, file_id: int) -> DownloadLink:
            assert file_id == 42
            return DownloadLink("https://www.opensubtitles.com/download/test.srt", "test.srt")

        async def download_srt(self, link: DownloadLink) -> bytes:
            assert link.file_name == "test.srt"
            return validate_srt(VALID_SRT)

    monkeypatch.setattr(subtitle_handler, "OpenSubtitlesClient", FakeOpenSubtitlesClient)
    monkeypatch.setattr(
        subtitle_handler,
        "get_settings",
        lambda: SimpleNamespace(opensubtitles_api_key=SecretStr("test-api-key")),
    )

    conversation_store._conversations.clear()
    conversation = conversation_store.get(7)
    conversation.language = SubtitleLanguage.ENGLISH
    conversation.selected_title = "Inception"
    workflow_id = conversation.workflow_id
    result = SubtitleResult(42, "WEBRip", "srt", False, 10, 8.0, "<b>uploader</b>")
    delivered_path: Path | None = None

    async def capture_document(document: object, *, caption: str) -> None:
        nonlocal delivered_path
        delivered_path = Path(document.path)  # type: ignore[attr-defined]
        assert delivered_path.exists()
        assert document.filename == "Inception-en.srt"  # type: ignore[attr-defined]
        assert "OpenSubtitles.com" in caption
        assert "&lt;b&gt;uploader&lt;/b&gt;" in caption
        assert "<b>uploader</b>" not in caption

    message = SimpleNamespace(
        answer=AsyncMock(),
        answer_document=AsyncMock(side_effect=capture_document),
    )

    asyncio.run(deliver_subtitle(message, 7, workflow_id, result))  # type: ignore[arg-type]

    assert delivered_path is not None
    assert not delivered_path.exists()
    message.answer_document.assert_awaited_once()
