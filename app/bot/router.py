"""Router composition for the Telegram application."""

from aiogram import Router

from app.bot.handlers import help, language, privacy, search, start, subtitle


def build_router() -> Router:
    """Build the root router with all public handlers."""
    router = Router(name="root")
    router.include_routers(
        start.router,
        language.router,
        search.router,
        subtitle.router,
        privacy.router,
        help.router,
    )
    return router
