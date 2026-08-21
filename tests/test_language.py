"""Language preference and workflow reset tests."""

import asyncio

from app.application.dto import WorkflowStage
from app.domain.languages import LanguageCode
from tests.support import build_test_application


def test_language_selection_is_durable_but_workflow_state_is_temporary() -> None:
    app = build_test_application()

    async def scenario() -> None:
        selected = await app.services.choose_language.execute(42, LanguageCode.PERSIAN)
        conversation = await app.conversations.get(42)
        assert conversation.stage is WorkflowStage.AWAITING_TITLE
        assert conversation.language is LanguageCode.PERSIAN

        await app.services.cancel_workflow.execute(42)
        cancelled = await app.conversations.get(42)
        assert cancelled.workflow_id != selected.workflow_id
        assert cancelled.stage is WorkflowStage.IDLE
        assert cancelled.language is LanguageCode.PERSIAN
        assert await app.preferences.get_language(42) is LanguageCode.PERSIAN

    asyncio.run(scenario())


def test_start_restores_preference_and_invalidates_old_workflow() -> None:
    app = build_test_application()

    async def scenario() -> None:
        old = await app.services.choose_language.execute(7, LanguageCode.ENGLISH)
        started = await app.services.start_search.execute(7)
        current = await app.conversations.get(7)
        assert started.language is LanguageCode.ENGLISH
        assert current.language is LanguageCode.ENGLISH
        assert current.workflow_id != old.workflow_id

    asyncio.run(scenario())
