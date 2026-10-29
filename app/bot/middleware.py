"""Load the durable interface preference before filters and handlers run."""

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.application.container import ApplicationServices
from app.bot.localization import interface_locale
from app.domain.errors import PreferenceUnavailableError
from app.domain.languages import InterfaceLanguage


class InterfaceLocaleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        services = data.get("services")
        user = getattr(event, "from_user", None)
        language = None
        if isinstance(services, ApplicationServices) and user is not None:
            try:
                language = await services.interface_preferences.get(user.id)
            except PreferenceUnavailableError:
                structlog.get_logger(__name__).warning("interface_preference_unavailable")
        with interface_locale(language or InterfaceLanguage.PERSIAN):
            return await handler(event, data)
