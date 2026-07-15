"""IP-based rate limiter using Redis fixed-window counters.

Uses existing redis[hiredis] — no new dependency.

Pattern: INCR key; set EXPIRE on first increment.  If count > max, return
HTTP 429 with Retry-After header.

Usage:
    from corpmind.core.rate_limit import make_rate_limiter

    _login_rl = make_rate_limiter("login", max_requests=10, window_seconds=900)

    @router.post("/login")
    async def login(
        _rl: None = Depends(_login_rl),
        ...
    ):
        ...

Key format:  rl:{scope}:{ip}
Redis TTL:   window_seconds (the fixed-window resets after one full window)
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable

import structlog
from fastapi import HTTPException, Request
from redis.asyncio import Redis

from corpmind.core.config import settings
from corpmind.core.redis import get_redis

log = structlog.get_logger(__name__)


def _client_ip(request: Request) -> str:
    """Extract the real client IP — trusts X-Forwarded-For behind a proxy."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def make_rate_limiter(
    scope: str,
    max_requests: int | None = None,
    window_seconds: int | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """Return a FastAPI-compatible async callable for the given rate-limit scope.

    The returned callable is designed to be used as a FastAPI dependency:
        _rl = make_rate_limiter("login", max_requests=10, window_seconds=900)

        @router.post("/login")
        async def login(_rl: None = Depends(_rl), ...):
            ...

    Falls back to settings defaults if max_requests / window_seconds are omitted.
    Fails OPEN on Redis errors — never blocks authentication due to infra issues.
    """
    _max = max_requests or settings.RATE_LIMIT_DEFAULT_MAX
    _window = window_seconds or settings.RATE_LIMIT_DEFAULT_WINDOW

    async def _check(request: Request) -> None:
        ip = _client_ip(request)
        key = f"rl:{scope}:{ip}"

        try:
            redis: Redis = get_redis()  # type: ignore[type-arg]
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, _window)

            if count > _max:
                ttl = await redis.ttl(key)
                retry_after = max(ttl, 1)
                log.warning(
                    "rate_limit.exceeded",
                    scope=scope,
                    ip=ip,
                    count=count,
                    max_requests=_max,
                    window_seconds=_window,
                    retry_after=retry_after,
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "rate_limit_exceeded",
                        "message": (
                            f"Too many requests. Limit: {_max} per "
                            f"{math.ceil(_window / 60)} minutes."
                        ),
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            log.debug(
                "rate_limit.checked",
                scope=scope,
                ip=ip,
                count=count,
                max_requests=_max,
            )

        except HTTPException:
            raise
        except Exception as exc:
            # Redis unavailable — fail open with a warning, never block auth
            log.warning(
                "rate_limit.redis_error",
                scope=scope,
                ip=ip,
                error=str(exc),
            )

    return _check
