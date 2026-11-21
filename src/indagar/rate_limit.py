from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

import httpx

RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class RetryPolicy:
    """Exponential backoff for transient HTTP failures."""

    def __init__(
        self,
        max_retries: int = 2,
        base_seconds: float = 0.5,
        max_seconds: float = 8.0,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ):
        self.max_retries = max(0, max_retries)
        self.base_seconds = max(0.0, base_seconds)
        self.max_seconds = max(0.0, max_seconds)
        self._sleep = sleep
        self._rng = rng

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
                await self._sleep(self._delay(attempt))
                continue

            if response.status_code not in RETRY_STATUSES:
                return response
            if attempt >= self.max_retries:
                return response
            await self._sleep(self._retry_after(response) or self._delay(attempt))

        raise AssertionError("retry loop exhausted without a response")

    def _delay(self, attempt: int) -> float:
        delay = min(self.max_seconds, self.base_seconds * (2**attempt))
        return delay * (0.5 + self._rng() / 2)

    def _retry_after(self, response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        if value < 0:
            return None
        return min(self.max_seconds, value)


class RateLimiter:
    """Space requests by a minimum interval, sharing one lock."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.min_interval = max(0.0, min_interval)
        self._clock = clock
        self._sleep = sleep
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            now = self._clock()
            delay = self._next_at - now
            if delay > 0:
                await self._sleep(delay)
            self._next_at = self._clock() + self.min_interval


__all__ = ["RETRY_STATUSES", "RateLimiter", "RetryPolicy"]
