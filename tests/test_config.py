"""Tests for configuration safeguards."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_accepts_a_non_placeholder_token() -> None:
    settings = Settings(telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz")

    assert settings.telegram_bot_token.get_secret_value().startswith("123456:")
    assert settings.log_level == "INFO"


def test_settings_rejects_example_token() -> None:
    with pytest.raises(ValidationError, match="real BotFather token"):
        Settings(telegram_bot_token="replace-with-your-bot-token")
