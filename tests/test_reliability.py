"""Tests for retries, redaction, health probes, monitoring, and notices."""

import asyncio
import json
from unittest.mock import AsyncMock

import structlog

from app.bot.handlers.privacy import PRIVACY_NOTICE, privacy_command
from app.core.config import Settings
from app.core.health import HealthServer
from app.core.logging import configure_logging, redact_sensitive, user_reference
from app.core.monitoring import Monitoring
from app.core.retry import retry_async


class TransientFailure(Exception):
    pass


def test_retry_uses_bounded_attempts_before_success() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientFailure
        return "ok"

    result = asyncio.run(
        retry_async(
            operation,
            (TransientFailure,),
            attempts=3,
            base_delay=0,
            jitter=0,
        )
    )

    assert result == "ok"
    assert calls == 3


def test_sensitive_log_fields_and_embedded_credentials_are_redacted() -> None:
    token = "123456789:abcdefghijklmnopqrstuvwxyz_ABCDE"
    event = redact_sensitive(
        object(),
        "info",
        {
            "event": f"request failed near {token}",
            "api_key": "private",
            "query": "private movie title",
            "database": "postgresql://user:password@database/app",
        },
    )

    assert event["api_key"] == "[REDACTED]"
    assert event["query"] == "[REDACTED]"
    assert token not in event["event"]
    assert "password" not in event["database"]


def test_structured_logger_writes_json_without_secret_fields(capsys: object) -> None:
    configure_logging("INFO")
    structlog.get_logger("test").info("safe_event", token="private")

    output = capsys.readouterr().out  # type: ignore[attr-defined]
    payload = json.loads(output)
    assert payload["event"] == "safe_event"
    assert payload["token"] == "[REDACTED]"


def test_user_log_reference_does_not_expose_telegram_id() -> None:
    reference = user_reference(123456789)

    assert reference != "123456789"
    assert len(reference) == 12


def test_readiness_requires_provider_configuration() -> None:
    settings = Settings(telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz")

    async def healthy() -> dict[str, str | bool]:
        return {"redis": "disabled", "postgres": "disabled", "ready": True}

    server = HealthServer(settings, healthy)
    response = asyncio.run(server.ready(None))  # type: ignore[arg-type]
    payload = json.loads(response.text)

    assert response.status == 503
    assert payload["status"] == "degraded"
    assert payload["providers"] == {"tmdb": "missing", "opensubtitles": "missing"}


def test_monitoring_renders_low_cardinality_prometheus_counters() -> None:
    metrics = Monitoring()
    metrics.increment("provider_errors", "opensubtitles")

    rendered = metrics.render()

    assert "subtitle_bot_up 1" in rendered
    assert 'subtitle_bot_provider_errors_total{component="opensubtitles"} 1' in rendered


def test_privacy_command_includes_provider_and_copyright_notice() -> None:
    message = type("MessageStub", (), {"answer": AsyncMock()})()

    asyncio.run(privacy_command(message))  # type: ignore[arg-type]

    assert "OpenSubtitles.com" in PRIVACY_NOTICE
    assert "Copyright" in PRIVACY_NOTICE
    message.answer.assert_awaited_once_with(PRIVACY_NOTICE)
