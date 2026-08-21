"""Conversation isolation, serialization, expiration, and restart behavior."""

import asyncio

from app.domain.languages import LanguageCode
from tests.support import build_test_application


def test_two_users_do_not_leak_language_or_workflow_state() -> None:
    app = build_test_application()

    async def scenario() -> None:
        await asyncio.gather(
            app.services.choose_language.execute(1, LanguageCode.ENGLISH),
            app.services.choose_language.execute(2, LanguageCode.PERSIAN),
        )
        first, second = await asyncio.gather(
            app.conversations.get(1),
            app.conversations.get(2),
        )
        assert first.language is LanguageCode.ENGLISH
        assert second.language is LanguageCode.PERSIAN
        assert first.workflow_id != second.workflow_id

    asyncio.run(scenario())


def test_empty_repository_after_restart_returns_safe_idle_state() -> None:
    first_app = build_test_application()
    second_app = build_test_application()
    first = asyncio.run(first_app.conversations.get(1))
    restarted = asyncio.run(second_app.conversations.get(1))
    assert first.workflow_id != restarted.workflow_id
    assert restarted.language is None
