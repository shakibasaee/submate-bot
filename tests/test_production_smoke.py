"""Regression tests for the production smoke path and composition lifecycle."""

import asyncio
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bootstrap import ApplicationRuntime, build_runtime
from app.core.config import Settings
from scripts import production_smoke

ROOT = Path(__file__).resolve().parents[1]
VALID_TOKEN = "123456:abcdefghijklmnopqrstuvwxyz"


class FakeRuntime:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.closed = False

    async def health(self) -> dict[str, str | bool]:
        return {"redis": "disabled", "postgres": "disabled", "ready": self.ready}

    async def close(self) -> None:
        self.closed = True


def smoke_settings() -> Settings:
    return Settings(
        telegram_bot_token=VALID_TOKEN,
        tmdb_api_key="test-tmdb-key",
        opensubtitles_api_key="test-opensubtitles-key",
        opensubtitles_username="test-opensubtitles-user",
        opensubtitles_password="test-opensubtitles-password",
        database_url=None,
        redis_url=None,
    )


def test_smoke_module_uses_the_current_composition_root() -> None:
    module = importlib.import_module("scripts.production_smoke")
    source = (ROOT / "scripts" / "production_smoke.py").read_text(encoding="utf-8")
    runtime_default = inspect.signature(module.smoke).parameters["runtime_factory"].default

    assert "app.core.infrastructure" not in source
    assert runtime_default is build_runtime


def test_smoke_requires_opensubtitles_download_credentials() -> None:
    settings = Settings(
        telegram_bot_token=VALID_TOKEN,
        tmdb_api_key="test-tmdb-key",
        opensubtitles_api_key="test-opensubtitles-key",
    )

    assert not production_smoke.providers_are_configured(settings)
    assert production_smoke.providers_are_configured(smoke_settings())


def test_smoke_constructs_and_closes_the_real_runtime_without_network() -> None:
    settings = smoke_settings()
    created: list[ApplicationRuntime] = []

    async def runtime_factory(config: Settings) -> ApplicationRuntime:
        assert config is settings
        runtime = await build_runtime(config)
        created.append(runtime)
        return runtime

    async def telegram_check(token: str) -> int:
        assert token == VALID_TOKEN
        return 42

    asyncio.run(
        production_smoke.smoke(
            settings,
            runtime_factory=runtime_factory,
            telegram_check=telegram_check,
        )
    )

    assert len(created) == 1
    assert created[0].http_session.closed


def test_smoke_closes_injected_runtime_after_external_failure() -> None:
    runtime = FakeRuntime()

    async def runtime_factory(_settings: Settings) -> FakeRuntime:
        return runtime

    async def failing_telegram_check(_token: str) -> int:
        raise RuntimeError("Telegram unavailable")

    with pytest.raises(RuntimeError, match="Telegram unavailable"):
        asyncio.run(
            production_smoke.smoke(
                smoke_settings(),
                runtime_factory=runtime_factory,
                telegram_check=failing_telegram_check,
            )
        )

    assert runtime.closed


def test_telegram_check_closes_bot_session(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions: list[SimpleNamespace] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            assert token == VALID_TOKEN
            self.session = SimpleNamespace(close=self.close)
            sessions.append(self.session)

        async def get_me(self) -> SimpleNamespace:
            return SimpleNamespace(id=42)

        async def close(self) -> None:
            self.session.closed = True

    monkeypatch.setattr(production_smoke, "Bot", FakeBot)

    assert asyncio.run(production_smoke.authenticate_telegram(VALID_TOKEN)) == 42
    assert sessions[0].closed is True
