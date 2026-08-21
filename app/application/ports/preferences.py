"""Durable user preference contract."""

from typing import Protocol

from app.domain.languages import LanguageCode


class PreferenceRepository(Protocol):
    async def get_language(self, user_id: int) -> LanguageCode | None: ...

    async def set_language(self, user_id: int, language: LanguageCode) -> None: ...

    async def close(self) -> None: ...
