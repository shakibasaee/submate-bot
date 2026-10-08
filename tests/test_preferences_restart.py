"""Local preferences survive a repository/process replacement."""

import asyncio

from app.domain.languages import LanguageCode
from app.infrastructure.persistence.sqlite import SqlitePreferenceRepository


def test_sqlite_preferences_survive_restart(tmp_path):
    path = str(tmp_path / "preferences.sqlite3")

    async def scenario():
        first = SqlitePreferenceRepository(path)
        await first.set_language(12, LanguageCode.PERSIAN)
        await first.close()
        second = SqlitePreferenceRepository(path)
        assert await second.get_language(12) is LanguageCode.PERSIAN
        assert await second.get_language(99) is None
        await second.set_language(12, LanguageCode.ENGLISH)
        assert await SqlitePreferenceRepository(path).get_language(12) is LanguageCode.ENGLISH

    asyncio.run(scenario())
