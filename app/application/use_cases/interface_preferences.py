"""Independent interface preference and single-use language picker tokens."""

from uuid import uuid4

from app.application.dto import InterfaceChoiceOutcome
from app.application.ports.conversations import ConversationRepository
from app.application.ports.locks import UserLockManager
from app.application.ports.preferences import PreferenceRepository
from app.domain.errors import PreferenceUnavailableError, WorkflowExpiredError
from app.domain.languages import InterfaceLanguage, find_languages


class InterfacePreferences:
    def __init__(
        self,
        conversations: ConversationRepository,
        preferences: PreferenceRepository,
        locks: UserLockManager,
    ) -> None:
        self._conversations = conversations
        self._preferences = preferences
        self._locks = locks

    async def get(self, user_id: int) -> InterfaceLanguage | None:
        try:
            return await self._preferences.get_interface_language(user_id)
        except Exception:
            raise PreferenceUnavailableError("Interface preferences are unavailable.") from None

    async def open_picker(self, user_id: int) -> InterfaceChoiceOutcome:
        async with self._locks.hold(user_id):
            try:
                language = await self._preferences.get_interface_language(user_id)
                subtitle = await self._preferences.get_language(user_id)
            except Exception:
                raise PreferenceUnavailableError("Preferences are unavailable.") from None
            current = await self._conversations.get(user_id)
            picker_id = uuid4().hex
            await self._conversations.save(current.evolve(interface_picker_id=picker_id))
            return InterfaceChoiceOutcome(language, subtitle, picker_id)

    async def choose(
        self, user_id: int, picker_id: str, language: InterfaceLanguage
    ) -> InterfaceChoiceOutcome:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.interface_picker_id != picker_id:
                raise WorkflowExpiredError("This interface picker expired. Use /settings.")
            try:
                subtitle = await self._preferences.get_language(user_id)
                await self._preferences.set_interface_language(user_id, language)
            except Exception:
                raise PreferenceUnavailableError("Preferences could not be saved.") from None
            await self._conversations.save(
                current.evolve(interface_picker_id=None, subtitle_picker_open=False)
            )
            return InterfaceChoiceOutcome(language, subtitle)

    async def is_picker_open(self, user_id: int) -> bool:
        async with self._locks.hold(user_id):
            return (await self._conversations.get(user_id)).interface_picker_id is not None

    async def filter_picker(
        self, user_id: int, query: str
    ) -> tuple[InterfaceChoiceOutcome, tuple[InterfaceLanguage, ...]]:
        async with self._locks.hold(user_id):
            current = await self._conversations.get(user_id)
            if current.interface_picker_id is None:
                raise WorkflowExpiredError("Interface picker expired.")
            picker_id = uuid4().hex
            await self._conversations.save(current.evolve(interface_picker_id=picker_id))
            matches = tuple(
                InterfaceLanguage(code.value)
                for code in find_languages(query[:80])
                if code.value in {locale.value for locale in InterfaceLanguage}
            )
            return InterfaceChoiceOutcome(
                await self.get(user_id), current.language, picker_id
            ), matches
