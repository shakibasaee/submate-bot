"""Validate production dependencies and authenticate with the real Telegram API."""

import asyncio

import structlog
from aiogram import Bot

from app.core.config import get_settings
from app.core.infrastructure import infrastructure
from app.core.logging import configure_logging


async def smoke() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger(__name__)
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    try:
        await infrastructure.start(settings)
        health = await infrastructure.health()
        if not health.pop("ready"):
            logger.error("production_smoke_dependencies_failed", dependencies=health)
            raise SystemExit(1)
        providers_configured = all(
            secret is not None and not secret.get_secret_value().startswith("replace-")
            for secret in (settings.tmdb_api_key, settings.opensubtitles_api_key)
        )
        if not providers_configured:
            logger.error("production_smoke_provider_configuration_failed")
            raise SystemExit(1)
        async with asyncio.timeout(15):
            identity = await bot.get_me()
        logger.info(
            "production_smoke_succeeded",
            telegram_authenticated=True,
            bot_id=identity.id,
            dependencies=health,
        )
    finally:
        await infrastructure.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(smoke())
