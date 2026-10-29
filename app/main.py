"""Application entry point for long-polling Telegram execution."""

import asyncio
from contextlib import AsyncExitStack

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.utils.backoff import BackoffConfig

from app.bootstrap import build_runtime
from app.bot.router import build_router
from app.core.config import get_settings
from app.core.health import HealthServer
from app.core.logging import configure_logging
from app.core.monitoring import monitoring
from app.core.polling_lock import polling_lock
from app.core.retry import retry_async


async def wait_for_telegram(bot: Bot) -> None:
    """Reconnect in bounded batches; credential rejection is deliberately not retried."""
    while True:
        try:
            await retry_async(
                bot.me,
                (TelegramNetworkError, TelegramServerError, TimeoutError),
                attempts=3,
                base_delay=1,
                max_delay=3,
            )
            return
        except (TelegramNetworkError, TelegramServerError, TimeoutError) as error:
            structlog.get_logger(__name__).warning(
                "telegram_startup_waiting_for_network", error_type=type(error).__name__
            )
            await asyncio.sleep(15)


async def run() -> None:
    """Create the bot and begin polling for Telegram updates."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger(__name__)

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        session=AiohttpSession(timeout=20),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(bot.session.close)
            dispatcher = Dispatcher()
            dispatcher.include_router(build_router())
            runtime = await build_runtime(settings)
            cleanup.push_async_callback(runtime.close)
            health_server = HealthServer(settings, runtime.health)
            cleanup.push_async_callback(health_server.close)
            await health_server.start()
            monitoring.increment("starts")
            logger.info("bot_starting", environment=settings.app_env)
            await wait_for_telegram(bot)
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
                demo_mode=settings.demo_mode,
            )
    except Exception as error:
        monitoring.increment("crashes")
        logger.critical("bot_crashed", error_type=type(error).__name__)
        raise
    finally:
        logger.info("bot_stopped")


def main() -> None:
    """Run the asynchronous bot process."""
    try:
        settings = get_settings()
        with polling_lock(settings.telegram_bot_token.get_secret_value()):
            asyncio.run(run())
    except KeyboardInterrupt:
        return
    except Exception as error:
        print(f"SubMate stopped: {type(error).__name__}. Check configuration and connectivity.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
