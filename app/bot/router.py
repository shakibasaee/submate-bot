"""Router composition for the Telegram application."""

from aiogram import Router

from app.bot.handlers import help, home, interface, language, privacy, search, start, subtitle
from app.bot.middleware import InterfaceLocaleMiddleware


def build_router() -> Router:
    """Build the root router with all public handlers."""
    router = Router(name="root")
    router.message.outer_middleware(InterfaceLocaleMiddleware())
    router.callback_query.outer_middleware(InterfaceLocaleMiddleware())
    router.include_routers(
        start.router,
        interface.router,
        language.router,
        home.router,
        search.router,
        subtitle.router,
        privacy.router,
        help.router,
    )
    return router
