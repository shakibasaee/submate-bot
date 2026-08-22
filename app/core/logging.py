"""Structured logging configuration."""

import hashlib
import logging
import re
import sys
from typing import Any

import structlog

SENSITIVE_KEY_PARTS = (
    "token",
    "authorization",
    "api_key",
    "username",
    "password",
    "secret",
    "database_url",
    "redis_url",
    "query",
    "message_text",
)
BOT_TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
URL_PASSWORD_PATTERN = re.compile(r"(\w+://[^:/\s]+:)[^@\s]+(@)")


def _redact_value(key: str, value: Any) -> Any:
    if any(part in key.casefold() for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            child_key: _redact_value(str(child_key), child) for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    if isinstance(value, str):
        value = BOT_TOKEN_PATTERN.sub("[REDACTED_TOKEN]", value)
        return URL_PASSWORD_PATTERN.sub(r"\1[REDACTED]\2", value)
    return value


def redact_sensitive(
    _logger: object, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Remove secrets and unnecessary private text from structured log fields."""
    return {key: _redact_value(key, value) for key, value in event_dict.items()}


def user_reference(user_id: int) -> str:
    """Return a stable non-reversible short reference for operational logs."""
    return hashlib.sha256(f"telegram-user:{user_id}".encode()).hexdigest()[:12]


def configure_logging(level: str) -> None:
    """Configure JSON logs for application and third-party logging alike."""
    numeric_level = getattr(logging, level, logging.INFO)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(numeric_level)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
