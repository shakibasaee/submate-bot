"""Tests for replaceable in-memory infrastructure adapters."""

import asyncio

from app.domain.languages import LanguageCode
from app.infrastructure.cache.memory import InMemoryCache, InMemoryRateLimiter
from app.infrastructure.persistence.memory import (
    InMemoryConversationRepository,
    InMemoryPreferenceRepository,
)


def test_cache_values_expire() -> None:
    clock = {"now": 0.0}
    cache = InMemoryCache(lambda: clock["now"])
    asyncio.run(cache.set("title", {"id": 1}, 10))
    assert asyncio.run(cache.get("title")) == {"id": 1}
    clock["now"] = 11
    assert asyncio.run(cache.get("title")) is None


def test_rate_limit_resets_and_reports_retry_after() -> None:
    clock = {"now": 0.0}
    limiter = InMemoryRateLimiter(lambda: clock["now"])
    assert asyncio.run(limiter.check("search", 1, 1, 60)).allowed
    denied = asyncio.run(limiter.check("search", 1, 1, 60))
    assert not denied.allowed
    assert denied.retry_after == 60
    clock["now"] = 61
    assert asyncio.run(limiter.check("search", 1, 1, 60)).allowed


def test_preferences_are_separate_from_expiring_conversation_state() -> None:
    preferences = InMemoryPreferenceRepository()
    conversations = InMemoryConversationRepository()
    asyncio.run(preferences.set_language(7, LanguageCode.PERSIAN))
    original = asyncio.run(conversations.get(7))
    reset = asyncio.run(conversations.reset_workflow(7))
    assert original.workflow_id != reset.workflow_id
    assert asyncio.run(preferences.get_language(7)) is LanguageCode.PERSIAN
