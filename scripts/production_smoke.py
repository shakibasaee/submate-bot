"""Validate the production composition root and Telegram authentication."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

import structlog
from aiogram import Bot

from app.bootstrap import build_runtime
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging


class SmokeRuntime(Protocol):
    """Minimal runtime lifecycle required by the production smoke check."""

    async def health(self) -> dict[str, str | bool]: ...

    async def close(self) -> None: ...


type RuntimeFactory = Callable[[Settings], Awaitable[SmokeRuntime]]
type TelegramCheck = Callable[[str], Awaitable[int]]


async def authenticate_telegram(token: str) -> int:
    """Authenticate one Bot API client and always close its HTTP session."""
    bot = Bot(token)
    try:
        identity = await bot.get_me()
        return identity.id
    finally:
        await bot.session.close()


def providers_are_configured(settings: Settings) -> bool:
    """Return whether both providers have non-placeholder credentials."""
    return all(
        secret is not None
        and bool(secret.get_secret_value().strip())
        and not secret.get_secret_value().strip().startswith("replace-")
        for secret in (
            settings.tmdb_api_key,
            settings.opensubtitles_api_key,
            settings.opensubtitles_username,
            settings.opensubtitles_password,
        )
    )


async def smoke(
    settings: Settings | None = None,
    *,
    runtime_factory: RuntimeFactory = build_runtime,
    telegram_check: TelegramCheck = authenticate_telegram,
) -> None:
    """Check configured dependencies through the current production composition root."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    logger = structlog.get_logger(__name__)
    runtime = await runtime_factory(resolved_settings)
    try:
        health = dict(await runtime.health())
        if health.pop("ready", False) is not True:
            logger.error("production_smoke_dependencies_failed", dependencies=health)
            raise SystemExit(1)
        if not providers_are_configured(resolved_settings):
            logger.error("production_smoke_provider_configuration_failed")
            raise SystemExit(1)
        async with asyncio.timeout(15):
            bot_id = await telegram_check(resolved_settings.telegram_bot_token.get_secret_value())
        logger.info(
            "production_smoke_succeeded",
            telegram_authenticated=True,
            bot_id=bot_id,
            dependencies=health,
        )
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(smoke())
