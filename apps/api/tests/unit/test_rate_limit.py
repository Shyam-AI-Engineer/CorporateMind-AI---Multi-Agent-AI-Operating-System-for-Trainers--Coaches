"""Unit tests for the Redis fixed-window rate limiter.

Covers:
  - First request within limit passes
  - Request at the limit passes
  - Request over the limit raises HTTP 429 with Retry-After header
  - IP extraction from X-Forwarded-For header
  - IP fallback to request.client.host
  - Fail-open: Redis errors do not block requests
  - Custom max_requests and window_seconds override defaults
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi import Request

from corpmind.core.rate_limit import make_rate_limiter


def _make_request(
    ip: str = "1.2.3.4",
    forwarded_for: str | None = None,
) -> Request:
    """Build a minimal mock Request."""
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    if forwarded_for is not None:
        req.headers = {"X-Forwarded-For": forwarded_for}
    return req


def _make_redis(
    incr_return: int = 1,
    ttl_return: int = 55,
    incr_raises: Exception | None = None,
) -> AsyncMock:
    """Build a mock Redis client."""
    redis = AsyncMock()
    if incr_raises is not None:
        redis.incr.side_effect = incr_raises
    else:
        redis.incr.return_value = incr_return
    redis.expire = AsyncMock()
    redis.ttl.return_value = ttl_return
    return redis


# ── Basic pass / block behaviour ───────────────────────────────────────────────

class TestRateLimitBasic:
    @pytest.mark.asyncio
    async def test_first_request_passes(self) -> None:
        """Count=1 — well under limit, no exception."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=1)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request())  # must not raise

    @pytest.mark.asyncio
    async def test_request_at_limit_passes(self) -> None:
        """Count == max_requests still passes (limit is exclusive)."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=5)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request())  # must not raise

    @pytest.mark.asyncio
    async def test_request_over_limit_raises_429(self) -> None:
        """Count > max_requests must raise HTTP 429."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=6, ttl_return=42)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await check(_make_request())

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_retry_after_header_present(self) -> None:
        """HTTP 429 must include Retry-After header derived from Redis TTL."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=6, ttl_return=37)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await check(_make_request())

        assert exc_info.value.headers is not None
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["Retry-After"] == "37"

    @pytest.mark.asyncio
    async def test_retry_after_minimum_one_second(self) -> None:
        """Retry-After is at least 1 even if Redis returns 0 or -1 TTL."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=10, ttl_return=0)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await check(_make_request())

        assert exc_info.value.headers["Retry-After"] == "1"

    @pytest.mark.asyncio
    async def test_expire_only_set_on_first_increment(self) -> None:
        """EXPIRE is called exactly once (when count == 1) to set the window."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=1)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request())

        redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expire_not_reset_on_subsequent_increments(self) -> None:
        """EXPIRE is NOT called on counts > 1 (avoids resetting the window)."""
        check = make_rate_limiter("test_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_return=3)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request())

        redis.expire.assert_not_awaited()


# ── IP extraction ──────────────────────────────────────────────────────────────

class TestClientIPExtraction:
    @pytest.mark.asyncio
    async def test_ip_from_client_host(self) -> None:
        """Without X-Forwarded-For, uses request.client.host."""
        check = make_rate_limiter("ip_scope", max_requests=100, window_seconds=60)
        redis = _make_redis(incr_return=1)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request(ip="10.0.0.1"))

        call_args = redis.incr.call_args[0][0]
        assert "10.0.0.1" in call_args

    @pytest.mark.asyncio
    async def test_ip_from_x_forwarded_for(self) -> None:
        """X-Forwarded-For first segment takes precedence over client.host."""
        check = make_rate_limiter("ip_scope", max_requests=100, window_seconds=60)
        redis = _make_redis(incr_return=1)
        req = _make_request(ip="10.0.0.1", forwarded_for="203.0.113.5, 10.0.0.1")

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(req)

        call_args = redis.incr.call_args[0][0]
        assert "203.0.113.5" in call_args
        assert "10.0.0.1" not in call_args

    @pytest.mark.asyncio
    async def test_different_ips_have_separate_counters(self) -> None:
        """Two different IPs are tracked independently (different Redis keys)."""
        check = make_rate_limiter("ip_scope", max_requests=2, window_seconds=60)
        redis = _make_redis(incr_return=1)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request(ip="1.1.1.1"))
            await check(_make_request(ip="2.2.2.2"))

        assert redis.incr.await_count == 2
        keys_used = [call[0][0] for call in redis.incr.call_args_list]
        assert keys_used[0] != keys_used[1]


# ── Fail-open ─────────────────────────────────────────────────────────────────

class TestFailOpen:
    @pytest.mark.asyncio
    async def test_redis_connection_error_does_not_block(self) -> None:
        """Redis errors must not block the request — fail open."""
        check = make_rate_limiter("fail_open_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_raises=ConnectionError("Redis unreachable"))

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            # Should NOT raise — fail open
            await check(_make_request())

    @pytest.mark.asyncio
    async def test_redis_timeout_does_not_block(self) -> None:
        """TimeoutError from Redis also fails open."""
        check = make_rate_limiter("fail_open_scope", max_requests=5, window_seconds=60)
        redis = _make_redis(incr_raises=TimeoutError("Redis timeout"))

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request())


# ── Scope isolation ────────────────────────────────────────────────────────────

class TestScopeIsolation:
    @pytest.mark.asyncio
    async def test_redis_key_includes_scope(self) -> None:
        """Redis key uses the limiter's scope so different endpoints don't share counters."""
        check = make_rate_limiter("login", max_requests=10, window_seconds=60)
        redis = _make_redis(incr_return=1)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            await check(_make_request())

        key = redis.incr.call_args[0][0]
        assert key.startswith("rl:login:")

    @pytest.mark.asyncio
    async def test_429_detail_contains_code(self) -> None:
        """HTTP 429 detail must include a 'code' field for API consumers."""
        check = make_rate_limiter("test_scope", max_requests=1, window_seconds=60)
        redis = _make_redis(incr_return=2, ttl_return=10)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await check(_make_request())

        assert isinstance(exc_info.value.detail, dict)
        assert exc_info.value.detail.get("code") == "rate_limit_exceeded"


# ── Settings-based defaults ────────────────────────────────────────────────────

class TestSettingsDefaults:
    @pytest.mark.asyncio
    async def test_defaults_from_settings_when_none_passed(self) -> None:
        """When max_requests/window_seconds are omitted, settings defaults are used."""
        check = make_rate_limiter("default_scope")
        redis = _make_redis(incr_return=1)

        with patch("corpmind.core.rate_limit.get_redis", return_value=redis):
            # Just confirm it runs without error (settings defaults apply)
            await check(_make_request())
