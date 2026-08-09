"""Typed application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets must be supplied through environment variables."""

    telegram_bot_token: SecretStr
    tmdb_api_key: SecretStr | None = None
    opensubtitles_api_key: SecretStr | None = None
    database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    tmdb_cache_ttl_seconds: int = 300
    subtitle_cache_ttl_seconds: int = 120
    user_search_limit_per_minute: int = 10
    global_tmdb_limit_per_minute: int = 120
    global_subtitle_limit_per_minute: int = 60
    user_download_limit_per_10_minutes: int = 5
    global_download_limit_per_minute: int = 20
    health_host: str = "0.0.0.0"
    health_port: int = Field(
        default=8080,
        validation_alias=AliasChoices("HEALTH_PORT", "PORT"),
    )
    telegram_tasks_concurrency_limit: int = 100
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("telegram_bot_token")
    @classmethod
    def token_must_not_be_placeholder(cls, value: SecretStr) -> SecretStr:
        """Fail early when the example token has not been replaced."""
        token = value.get_secret_value().strip()
        if not token or token == "replace-with-your-bot-token":
            raise ValueError("TELEGRAM_BOT_TOKEN must contain a real BotFather token")
        return SecretStr(token)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator(
        "tmdb_cache_ttl_seconds",
        "subtitle_cache_ttl_seconds",
        "user_search_limit_per_minute",
        "global_tmdb_limit_per_minute",
        "global_subtitle_limit_per_minute",
        "user_download_limit_per_10_minutes",
        "global_download_limit_per_minute",
        "health_port",
        "telegram_tasks_concurrency_limit",
    )
    @classmethod
    def integer_settings_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    # BaseSettings supplies required values from environment sources at runtime.
    return Settings()  # pyright: ignore[reportCallIssue]
