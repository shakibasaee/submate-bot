"""Per-user serialization contract."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class UserLockManager(Protocol):
    def hold(self, user_id: int) -> AbstractAsyncContextManager[None]: ...
