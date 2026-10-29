"""Per-update interface locale, isolated across concurrent Telegram users."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.domain.languages import InterfaceLanguage

_interface_language = ContextVar("interface_language", default=InterfaceLanguage.PERSIAN)


def current_interface_language() -> InterfaceLanguage:
    return _interface_language.get()


@contextmanager
def interface_locale(language: InterfaceLanguage) -> Iterator[None]:
    token = _interface_language.set(language)
    try:
        yield
    finally:
        _interface_language.reset(token)
