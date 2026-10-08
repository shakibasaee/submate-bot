"""Local durable preferences; no search history or credentials are stored."""

import asyncio
import sqlite3
from pathlib import Path

from app.domain.languages import LanguageCode


class SqlitePreferenceRepository:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=5)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS preferences "
            "(user_id INTEGER PRIMARY KEY, language TEXT NOT NULL)"
        )
        return connection

    def _get(self, user_id: int) -> LanguageCode | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT language FROM preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
            return LanguageCode(row[0]) if row else None
        finally:
            connection.close()

    def _set(self, user_id: int, language: LanguageCode) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO preferences VALUES (?, ?) ON CONFLICT(user_id) "
                    "DO UPDATE SET language=excluded.language",
                    (user_id, str(language)),
                )
        finally:
            connection.close()

    async def get_language(self, user_id: int) -> LanguageCode | None:
        return await asyncio.to_thread(self._get, user_id)

    async def set_language(self, user_id: int, language: LanguageCode) -> None:
        await asyncio.to_thread(self._set, user_id, language)

    async def close(self) -> None:
        return None
