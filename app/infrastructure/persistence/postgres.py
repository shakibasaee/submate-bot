"""PostgreSQL language preference repository."""

from psycopg import Error as PsycopgError
from psycopg_pool import AsyncConnectionPool

from app.domain.languages import LanguageCode
from app.infrastructure.persistence.memory import InMemoryPreferenceRepository

PREFERENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_preferences (
    telegram_user_id BIGINT PRIMARY KEY,
    subtitle_language VARCHAR(8) NOT NULL CHECK (subtitle_language IN ('en', 'fa')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


class PostgresPreferenceRepository:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        fallback: InMemoryPreferenceRepository,
    ) -> None:
        self._pool = pool
        self._fallback = fallback

    async def ensure_schema(self) -> None:
        async with self._pool.connection(timeout=3) as connection:
            await connection.execute(PREFERENCE_SCHEMA)

    async def get_language(self, user_id: int) -> LanguageCode | None:
        try:
            async with self._pool.connection(timeout=3) as connection:
                cursor = await connection.execute(
                    "SELECT subtitle_language FROM user_preferences WHERE telegram_user_id = %s",
                    (user_id,),
                )
                row = await cursor.fetchone()
            if row and row[0] in {item.value for item in LanguageCode}:
                language = LanguageCode(str(row[0]))
                await self._fallback.set_language(user_id, language)
                return language
        except (PsycopgError, TimeoutError):
            pass
        return await self._fallback.get_language(user_id)

    async def set_language(self, user_id: int, language: LanguageCode) -> None:
        await self._fallback.set_language(user_id, language)
        try:
            async with self._pool.connection(timeout=3) as connection:
                await connection.execute(
                    """
                    INSERT INTO user_preferences (telegram_user_id, subtitle_language)
                    VALUES (%s, %s)
                    ON CONFLICT (telegram_user_id) DO UPDATE
                    SET subtitle_language = EXCLUDED.subtitle_language, updated_at = NOW()
                    """,
                    (user_id, str(language)),
                )
        except (PsycopgError, TimeoutError):
            return

    async def close(self) -> None:
        return None
