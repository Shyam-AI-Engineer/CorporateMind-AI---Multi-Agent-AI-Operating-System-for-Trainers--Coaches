"""Unit tests for the enhanced /healthz handler.

Covers:
  - Returns HTTP 200 in all cases (even when dependencies are degraded)
  - Body contains status, version, dependencies, response_time_ms fields
  - DB 'ok' when SELECT 1 succeeds
  - DB 'error' when the engine raises
  - DB 'not_initialized' when get_engine() raises RuntimeError
  - Redis 'ok' when PING succeeds
  - Redis 'error' when the connection raises
  - Redis 'not_initialized' when get_redis() raises RuntimeError
  - overall status is 'ok' only when both deps are ok
  - overall status is 'degraded' when either dep fails
  - response_time_ms is a non-negative float
  - version field is a string
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.health import healthz_handler


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_engine(raises: Exception | None = None) -> MagicMock:
    """Return a mock SQLAlchemy async engine.

    The engine's connect() returns an async context manager whose __aenter__
    resolves to a connection that can execute().
    """
    conn = AsyncMock()
    if raises is not None:
        conn.execute.side_effect = raises
    else:
        conn.execute.return_value = MagicMock()

    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None

    engine = MagicMock()
    engine.connect.return_value = cm
    return engine


def _make_redis(raises: Exception | None = None) -> AsyncMock:
    redis = AsyncMock()
    if raises is not None:
        redis.ping.side_effect = raises
    return redis


# ── Response contract ─────────────────────────────────────────────────────────

class TestHealthzResponseContract:
    @pytest.mark.asyncio
    async def test_returns_http_200_when_all_ok(self) -> None:
        """Healthy state must return HTTP 200."""
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_http_200_when_db_degraded(self) -> None:
        """Even with a DB failure, response is HTTP 200 (load-balancer-friendly)."""
        engine = _make_engine(raises=Exception("DB connection refused"))
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_http_200_when_redis_degraded(self) -> None:
        """Redis failure must not result in a non-200 status."""
        engine = _make_engine()
        redis = _make_redis(raises=Exception("Redis unreachable"))

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_body_has_required_top_level_fields(self) -> None:
        """Body must include status, version, dependencies, response_time_ms."""
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert "status" in body
        assert "version" in body
        assert "dependencies" in body
        assert "response_time_ms" in body

    @pytest.mark.asyncio
    async def test_dependencies_has_database_and_redis(self) -> None:
        """dependencies block must include 'database' and 'redis' keys."""
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert "database" in body["dependencies"]
        assert "redis" in body["dependencies"]

    @pytest.mark.asyncio
    async def test_version_is_string(self) -> None:
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert isinstance(body["version"], str)
        assert len(body["version"]) > 0

    @pytest.mark.asyncio
    async def test_response_time_ms_is_non_negative_float(self) -> None:
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert isinstance(body["response_time_ms"], (int, float))
        assert body["response_time_ms"] >= 0


# ── Database dependency ────────────────────────────────────────────────────────

class TestDatabaseCheck:
    @pytest.mark.asyncio
    async def test_db_ok_when_select_1_succeeds(self) -> None:
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["dependencies"]["database"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_db_error_when_engine_raises(self) -> None:
        engine = _make_engine(raises=Exception("FATAL: connection refused"))
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["dependencies"]["database"]["status"] == "error"
        assert "detail" in body["dependencies"]["database"]

    @pytest.mark.asyncio
    async def test_db_not_initialized_when_get_engine_raises_runtime_error(self) -> None:
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", side_effect=RuntimeError("Not initialized")), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["dependencies"]["database"]["status"] == "not_initialized"


# ── Redis dependency ───────────────────────────────────────────────────────────

class TestRedisCheck:
    @pytest.mark.asyncio
    async def test_redis_ok_when_ping_succeeds(self) -> None:
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["dependencies"]["redis"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_redis_error_when_ping_raises(self) -> None:
        engine = _make_engine()
        redis = _make_redis(raises=ConnectionError("Redis down"))

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["dependencies"]["redis"]["status"] == "error"
        assert "detail" in body["dependencies"]["redis"]

    @pytest.mark.asyncio
    async def test_redis_not_initialized_when_get_redis_raises_runtime_error(self) -> None:
        engine = _make_engine()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", side_effect=RuntimeError("Not initialized")):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["dependencies"]["redis"]["status"] == "not_initialized"


# ── Overall status aggregation ─────────────────────────────────────────────────

class TestOverallStatus:
    @pytest.mark.asyncio
    async def test_overall_ok_when_both_deps_ok(self) -> None:
        engine = _make_engine()
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_overall_degraded_when_db_fails(self) -> None:
        engine = _make_engine(raises=Exception("DB error"))
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_overall_degraded_when_redis_fails(self) -> None:
        engine = _make_engine()
        redis = _make_redis(raises=Exception("Redis error"))

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_overall_degraded_when_both_deps_fail(self) -> None:
        engine = _make_engine(raises=Exception("DB error"))
        redis = _make_redis(raises=Exception("Redis error"))

        with patch("corpmind.core.database.get_engine", return_value=engine), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_overall_degraded_when_not_initialized(self) -> None:
        """Pre-startup probes (not_initialized) also result in 'degraded' overall."""
        redis = _make_redis()

        with patch("corpmind.core.database.get_engine", side_effect=RuntimeError("Not initialized")), \
             patch("corpmind.core.redis.get_redis", return_value=redis):
            response = await healthz_handler()

        import json
        body = json.loads(bytes(response.body))
        assert body["status"] == "degraded"
