from __future__ import annotations

import asyncio

import httpx

from indagar.rate_limit import RateLimiter, RetryPolicy


def test_retry_honours_retry_after():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"retry-after": "0.2"})
        return httpx.Response(200, json={"ok": True})

    async def run() -> tuple[httpx.Response, list[float]]:
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            policy = RetryPolicy(max_retries=2, sleep=sleep)
            response = await policy.request(client, "GET", "https://example.com")
        return response, sleeps

    response, sleeps = asyncio.run(run())

    assert response.status_code == 200
    assert calls["count"] == 2
    assert sleeps == [0.2]


def test_retry_ignores_non_transient_4xx():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, json={"error": "bad"})

    async def run() -> httpx.Response:
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            policy = RetryPolicy(max_retries=3, sleep=sleep)
            return await policy.request(client, "GET", "https://example.com")

    response = asyncio.run(run())

    assert response.status_code == 400
    assert calls["count"] == 1


def test_retry_stops_after_max_retries():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503)

    async def run() -> httpx.Response:
        async def sleep(delay: float) -> None:
            return None

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            policy = RetryPolicy(max_retries=2, base_seconds=0.0, sleep=sleep)
            return await policy.request(client, "GET", "https://example.com")

    response = asyncio.run(run())

    assert response.status_code == 503
    assert calls["count"] == 3


def test_retry_recovers_from_transport_error():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    async def run() -> httpx.Response:
        async def sleep(delay: float) -> None:
            return None

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            policy = RetryPolicy(max_retries=1, base_seconds=0.0, sleep=sleep)
            return await policy.request(client, "GET", "https://example.com")

    response = asyncio.run(run())

    assert response.status_code == 200
    assert calls["count"] == 2


def test_rate_limiter_spaces_requests():
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    limiter = RateLimiter(1.0, clock=clock, sleep=sleep)

    async def run() -> None:
        await limiter.wait()
        await limiter.wait()

    asyncio.run(run())

    assert sleeps == [1.0]
