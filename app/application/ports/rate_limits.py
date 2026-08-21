"""Rate-limit contract."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int | None = None


class RateLimiter(Protocol):
    async def check(
        self, scope: str, identifier: str | int, limit: int, window_seconds: int
    ) -> RateLimitDecision: ...
