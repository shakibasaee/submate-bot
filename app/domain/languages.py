"""Supported subtitle language identifiers."""

from enum import StrEnum


class LanguageCode(StrEnum):
    """Stable internal language codes independent of any provider."""

    ENGLISH = "en"
    PERSIAN = "fa"


class InterfaceLanguage(StrEnum):
    """A UI preference, never a subtitle-provider language selection."""

    ENGLISH = "en"
    PERSIAN = "fa"
