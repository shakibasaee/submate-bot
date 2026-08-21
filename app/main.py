"""Application entry point for long-polling Telegram execution."""

import asyncio

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.backoff import BackoffConfig

from app.bootstrap import ApplicationRuntime, build_runtime
from app.bot.router import build_router
from app.core.config import get_settings
from app.core.health import HealthServer
from app.core.logging import configure_logging
from app.core.monitoring import monitoring


async def run() -> None:
    """Create the bot and begin polling for Telegram updates."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger(__name__)

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router())
    runtime: ApplicationRuntime | None = None
    health_server: HealthServer | None = None

    try:
        runtime = await build_runtime(settings)
        health_server = HealthServer(settings, runtime.health)
        await health_server.start()
        monitoring.increment("starts")
        logger.info("bot_starting", environment=settings.app_env)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            backoff_config=BackoffConfig(
                min_delay=1.0,
                max_delay=10.0,
                factor=1.7,
                jitter=0.2,
            ),
            tasks_concurrency_limit=settings.telegram_tasks_concurrency_limit,
            close_bot_session=False,
            services=runtime.services,
        )
    except Exception as error:
        monitoring.increment("crashes")
        logger.critical("bot_crashed", error_type=type(error).__name__)
        raise
    finally:
        if health_server is not None:
            await health_server.close()
        if runtime is not None:
            await runtime.close()
        await bot.session.close()
        logger.info("bot_stopped")


def main() -> None:
    """Run the asynchronous bot process."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
