"""Composition-root HTTP ownership and shutdown tests."""

import asyncio

import pytest

from app import bootstrap
from app.bootstrap import build_runtime
from app.core.config import Settings


def test_runtime_closes_shared_http_session() -> None:
    settings = Settings(telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz")

    async def scenario() -> None:
        runtime = await build_runtime(settings)
        session = runtime.http_session
        assert not session.closed
        await runtime.close()
        assert session.closed

    asyncio.run(scenario())


def test_partial_startup_failure_closes_shared_http_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(telegram_bot_token="123456:abcdefghijklmnopqrstuvwxyz")
    sessions: list[object] = []
    original = bootstrap.aiohttp.ClientSession

    def capture_session(*args: object, **kwargs: object):
        session = original(*args, **kwargs)
        sessions.append(session)
        return session

    def fail_services(*args: object, **kwargs: object):
        raise RuntimeError("composition failed")

    monkeypatch.setattr(bootstrap.aiohttp, "ClientSession", capture_session)
    monkeypatch.setattr(bootstrap, "ApplicationServices", fail_services)

    with pytest.raises(RuntimeError, match="composition failed"):
        asyncio.run(build_runtime(settings))

    assert len(sessions) == 1
    assert sessions[0].closed  # type: ignore[attr-defined]
