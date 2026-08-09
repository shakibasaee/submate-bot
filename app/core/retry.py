"""Small bounded async retry helper with exponential backoff and jitter."""

import asyncio
import random
from collections.abc import Awaitable, Callable


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    retry_on: tuple[type[BaseException], ...],
    *,
    attempts: int = 3,
    base_delay: float = 0.25,
    max_delay: float = 2.0,
    jitter: float = 0.2,
) -> T:
    """Retry transient failures with a strict attempt and delay ceiling."""
    if attempts < 1:
        raise ValueError("attempts must be at least one")
    for attempt in range(attempts):
        try:
            return await operation()
        except retry_on:
            if attempt == attempts - 1:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            delay += random.uniform(0, delay * jitter)
            await asyncio.sleep(delay)
    raise RuntimeError("retry loop ended unexpectedly")
