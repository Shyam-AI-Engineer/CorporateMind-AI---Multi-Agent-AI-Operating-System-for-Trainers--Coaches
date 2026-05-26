"""Async Redis client — shared connection pool for the whole application.

Usage:
    from corpmind.core.redis import get_redis

    redis = get_redis()
    await redis.set("key", "value", ex=300)

The pool is initialized at startup (init_redis) and closed at shutdown (close_redis).
Per-tenant key convention: t:{org_id}:{workspace_id}:{purpose}
"""

from __future__ import annotations

import structlog
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from corpmind.core.config import settings

log = structlog.get_logger(__name__)

_pool: ConnectionPool | None = None
_client: Redis | None = None  # type: ignore[type-arg]


async def init_redis() -> None:
    global _pool, _client
    _pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_POOL_SIZE,
        decode_responses=True,
    )
    _client = Redis(connection_pool=_pool)
    await _client.ping()
    log.info("redis.connected", url=settings.REDIS_URL)


async def close_redis() -> None:
    global _pool, _client
    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.aclose()
        _pool = None
    log.info("redis.disconnected")


def get_redis() -> Redis:  # type: ignore[type-arg]
    if _client is None:
        raise RuntimeError("Redis not initialized — call init_redis() first")
    return _client


# ── Refresh token jti helpers ──────────────────────────────────────────────────

_JTI_PREFIX = "auth:jti:blocklist:"
_JTI_TTL_SECONDS = 60 * 60 * 24 * 31  # 31 days (refresh token lifetime + 1 day buffer)


async def blocklist_jti(jti: str) -> None:
    """Mark a refresh token jti as revoked (used or logged-out)."""
    await get_redis().set(f"{_JTI_PREFIX}{jti}", "1", ex=_JTI_TTL_SECONDS)


async def is_jti_blocked(jti: str) -> bool:
    """Return True if this jti has been revoked."""
    return await get_redis().exists(f"{_JTI_PREFIX}{jti}") == 1
