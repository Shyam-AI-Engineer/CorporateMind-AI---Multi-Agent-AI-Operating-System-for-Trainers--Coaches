"""API-layer test fixtures.

Adds on top of the root conftest:
  - redis_client  — real Redis via testcontainers (session-scoped)
  - api_client    — httpx AsyncClient with DB + Redis dep overrides (function-scoped)
  - make_user()   — coroutine helper: POST /register a fresh user, return tokens + payload

Redis is wired by patching corpmind.core.redis._client directly; the module
uses a singleton that is normally initialized via init_redis() in the app
lifespan, which ASGITransport does not call.

Database sessions are provided via FastAPI dependency_overrides on
get_session / get_public_session so every request uses the testcontainer
Postgres rather than the production DATABASE_URL.  SET ROLE corpmind_test
is issued at session start so PostgreSQL enforces RLS policies (the
postgres superuser bypasses them without this).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


# ── Redis testcontainer ────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def redis_client(db_engine: AsyncEngine) -> AsyncGenerator[object, None]:
    """Start a Redis testcontainer and patch it into corpmind.core.redis."""
    try:
        from testcontainers.redis import RedisContainer
        import corpmind.core.redis as _redis_mod
        from redis.asyncio import Redis as AIORedis

        with RedisContainer("redis:7-alpine") as rc:
            port = rc.get_exposed_port(6379)
            client: AIORedis = AIORedis.from_url(  # type: ignore[type-arg]
                f"redis://localhost:{port}", decode_responses=True
            )
            await client.ping()
            _redis_mod._client = client  # type: ignore[assignment]
            yield client
            await client.aclose()
            _redis_mod._client = None  # type: ignore[assignment]

    except ImportError:
        pytest.skip("testcontainers[redis] not available")


# ── HTTP client with wired deps ────────────────────────────────────────────────

@pytest_asyncio.fixture
async def api_client(
    db_engine: AsyncEngine, redis_client: object
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient pointing at the FastAPI app with testcontainer DB + Redis.

    Overrides get_public_session (register, login, refresh) and get_session
    (authenticated routes) so every request uses the test Postgres engine
    instead of the production DATABASE_URL.

    dependency_overrides are cleared in teardown so tests cannot bleed into
    each other even when they fail mid-way.
    """
    from corpmind.core.database import get_public_session, get_session
    from corpmind.main import app

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _public_session() -> AsyncGenerator:
        async with factory() as session:
            await session.execute(text("SET ROLE corpmind_test"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _authed_session() -> AsyncGenerator:
        from corpmind.core.tenancy import get_tenant_context
        async with factory() as session:
            await session.execute(text("SET ROLE corpmind_test"))
            ctx = get_tenant_context()
            await session.execute(
                text(f"SET LOCAL app.tenant_id = '{ctx.org_id}'")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_public_session] = _public_session
    app.dependency_overrides[get_session] = _authed_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ── User factory helper ────────────────────────────────────────────────────────

async def make_user(client: AsyncClient) -> dict:
    """Register a unique user and return {"tokens": TokenResponse, "payload": RegisterRequest}.

    Each call generates a distinct email / org so tests that call make_user()
    multiple times get fully isolated tenants.
    """
    uid = uuid.uuid4().hex[:8]
    payload = {
        "email": f"user-{uid}@example.com",
        "password": "Str0ngP@ss!",
        "full_name": f"Test User {uid}",
        "org_name": f"Test Org {uid}",
    }
    resp = await client.post("/api/v1/identity/register", json=payload)
    assert resp.status_code == 201, f"make_user failed: {resp.text}"
    return {"tokens": resp.json(), "payload": payload}
