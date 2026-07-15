"""Enhanced /healthz handler — DB, Redis, and version checks.

Design rules:
  • No expensive queries. DB check is SELECT 1 only. Redis check is PING only.
  • Never raises — all dependency checks are wrapped in try/except so the
    endpoint always responds (even when dependencies are degraded).
  • Returns 200 when the process is healthy regardless of dependency state.
    A 200 with dep_status=degraded is intentional: the process is alive and
    load balancers should keep routing to it.  A 503 would cause the LB to
    drain the instance, which is correct only for total failure.
  • Response time is measured for the full dependency check round trip and
    returned in milliseconds.
"""

from __future__ import annotations

import importlib.metadata
import time
from typing import Any

import structlog
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)

# Version from package metadata (set in pyproject.toml); falls back to "dev".
try:
    _VERSION = importlib.metadata.version("corpmind-api")
except importlib.metadata.PackageNotFoundError:
    _VERSION = "dev"


async def _check_db() -> dict[str, Any]:
    """Run SELECT 1 against the primary Postgres pool."""
    from sqlalchemy import text
    from corpmind.core.database import get_engine
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except RuntimeError:
        # Engine not initialized yet (pre-startup probe)
        return {"status": "not_initialized"}
    except Exception as exc:
        log.warning("health.db_check_failed", error=str(exc))
        return {"status": "error", "detail": type(exc).__name__}


async def _check_redis() -> dict[str, Any]:
    """Send PING to the Redis pool."""
    from corpmind.core.redis import get_redis
    try:
        redis = get_redis()
        await redis.ping()
        return {"status": "ok"}
    except RuntimeError:
        return {"status": "not_initialized"}
    except Exception as exc:
        log.warning("health.redis_check_failed", error=str(exc))
        return {"status": "error", "detail": type(exc).__name__}


async def healthz_handler() -> JSONResponse:
    """Production-ready health check.

    Checks:
      - Database connectivity (SELECT 1)
      - Redis connectivity (PING)
      - Version / build info
      - Total response time (ms)

    Always returns HTTP 200 so load balancers keep the instance in rotation.
    The ``status`` field in the JSON body conveys the true health state.
    """
    t0 = time.monotonic()

    db_result, redis_result = await _check_db(), await _check_redis()

    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

    all_ok = db_result["status"] == "ok" and redis_result["status"] == "ok"
    overall = "ok" if all_ok else "degraded"

    body: dict[str, Any] = {
        "status": overall,
        "version": _VERSION,
        "dependencies": {
            "database": db_result,
            "redis": redis_result,
        },
        "response_time_ms": elapsed_ms,
    }

    log.debug(
        "health.check",
        status=overall,
        db=db_result["status"],
        redis=redis_result["status"],
        response_time_ms=elapsed_ms,
    )

    return JSONResponse(content=body, status_code=200)
