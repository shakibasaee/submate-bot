"""Supported subtitle language identifiers."""

import re
import unicodedata
from enum import StrEnum


class LanguageCode(StrEnum):
    """Stable internal language codes independent of any provider."""

    ENGLISH = "en"
    PERSIAN = "fa"
    ARABIC = "ar"
    TURKISH = "tr"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    RUSSIAN = "ru"


class InterfaceLanguage(StrEnum):
    """A UI preference, never a subtitle-provider language selection."""

    ENGLISH = "en"
    PERSIAN = "fa"
    GERMAN = "de"
    RUSSIAN = "ru"


LANGUAGE_NAMES: dict[LanguageCode, tuple[str, str, str]] = {
    LanguageCode.PERSIAN: ("فارسی", "Persian", "farsi پارسی"),
    LanguageCode.ENGLISH: ("English", "انگلیسی", "english"),
    LanguageCode.ARABIC: ("العربية", "Arabic", "عربی"),
    LanguageCode.TURKISH: ("Türkçe", "Turkish", "ترکی turkce"),
    LanguageCode.SPANISH: ("Español", "Spanish", "اسپانیایی espanol"),
    LanguageCode.FRENCH: ("Français", "French", "فرانسوی francais"),
    LanguageCode.GERMAN: ("Deutsch", "German", "آلمانی"),
    LanguageCode.ITALIAN: ("Italiano", "Italian", "ایتالیایی"),
    LanguageCode.PORTUGUESE: ("Português", "Portuguese", "پرتغالی portugues"),
    LanguageCode.RUSSIAN: ("Русский", "Russian", "روسی"),
}


def normalize_language_query(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "\u200c": " "}))
    return " ".join(re.findall(r"\w+", value))


def find_languages(query: str) -> tuple[LanguageCode, ...]:
    key = normalize_language_query(query)
    if not key:
        return tuple(LANGUAGE_NAMES)
    return tuple(
        code
        for code, names in LANGUAGE_NAMES.items()
        if key == code or any(key in normalize_language_query(name) for name in names)
    )
