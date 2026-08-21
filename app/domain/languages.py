"""Supported subtitle language identifiers."""

from enum import StrEnum


class LanguageCode(StrEnum):
    """Stable internal language codes independent of any provider."""

    ENGLISH = "en"
    PERSIAN = "fa"
