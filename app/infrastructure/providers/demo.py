"""Explicit original sample captions; never a substitute for real subtitles."""

from uuid import uuid4

from app.domain.errors import ProviderNotFoundError, ProviderUnavailableError
from app.domain.languages import LanguageCode
from app.domain.subtitles import (
    DownloadedSubtitle,
    ProviderFileRef,
    ProviderId,
    SubtitleCandidate,
    SubtitleQuery,
)
from app.infrastructure.providers.opensubtitles import validate_srt


class DemoSubtitleProvider:
    provider_id = ProviderId("demo")

    def __init__(self) -> None:
        self._pending_failures: set[str] = set()

    async def search(self, query: SubtitleQuery) -> list[SubtitleCandidate]:
        reference = uuid4().hex
        if len(self._pending_failures) >= 128:
            self._pending_failures.pop()
        self._pending_failures.add(reference)
        return [
            SubtitleCandidate(
                self.provider_id,
                ProviderFileRef(f"sample-{query.language}"),
                query.language,
                "srt",
                "DEMO — original sample captions",
            ),
            SubtitleCandidate(
                self.provider_id,
                ProviderFileRef(f"retry-{reference}-{query.language}"),
                query.language,
                "srt",
                "DEMO — fails once, then Retry succeeds",
            ),
        ]

    async def download(self, candidate: SubtitleCandidate) -> DownloadedSubtitle:
        if candidate.provider_id != self.provider_id:
            raise ProviderNotFoundError("Unknown demo candidate")
        reference = str(candidate.provider_file_ref)
        if reference.startswith("retry-"):
            key = reference.split("-")[1]
            if key in self._pending_failures:
                self._pending_failures.remove(key)
                raise ProviderUnavailableError("Intentional demo failure; press Retry.")
        elif not reference.startswith("sample-"):
            raise ProviderNotFoundError("Unknown demo candidate")
        caption = (
            "این فایل فقط برای آزمایش ساب‌میت است؛ زیرنویس فیلم نیست."
            if candidate.language is LanguageCode.PERSIAN
            else "This is an original SubMate test caption, not a movie subtitle."
        )
        content = (
            "1\n00:00:01,000 --> 00:00:05,000\nDEMO — SAMPLE ONLY\n\n"
            f"2\n00:00:06,000 --> 00:00:12,000\n{caption}\n"
        )
        return DownloadedSubtitle(
            validate_srt(content.encode()),
            "demo.srt",
            "srt",
            "DEMO — original sample captions, not real movie dialogue.",
        )
