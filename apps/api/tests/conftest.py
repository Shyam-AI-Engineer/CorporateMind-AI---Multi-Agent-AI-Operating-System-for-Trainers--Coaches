"""Pytest configuration and fixtures for the CorporateMind AI test suite.

Test pyramid:
  unit/        — service logic, mocked repos
  repo/        — repository against real Postgres (testcontainers)
  api/         — HTTP endpoint tests (AsyncClient + testcontainers)
  integration/ — multi-step flows

All tests are async. Tenant isolation tests are in their own conftest.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from corpmind.core.tenancy import TenantContext


# ── Event loop policy ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── Test tenant helpers ────────────────────────────────────────────────────────

def make_tenant_ctx(
    *,
    org_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    role: str = "Trainer",
    plan_tier: str = "starter",
) -> TenantContext:
    return TenantContext(
        org_id=org_id or uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        role=role,
        request_id=str(uuid.uuid4()),
        plan_tier=plan_tier,
    )


@pytest.fixture
def tenant_ctx() -> TenantContext:
    return make_tenant_ctx()


@pytest.fixture
def tenant_a() -> TenantContext:
    return make_tenant_ctx()


@pytest.fixture
def tenant_b() -> TenantContext:
    return make_tenant_ctx()


# ── Alembic helper (runs in a thread to avoid event-loop conflict) ─────────────

def _run_alembic_upgrade(url: str) -> None:
    from alembic import command
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")


async def _setup_test_role(engine: AsyncEngine) -> None:
    """Create a non-superuser role so PostgreSQL enforces RLS in tests.

    Testcontainers connects as the postgres superuser, which bypasses all
    RLS policies.  SET ROLE to a non-superuser causes the policies to apply
    correctly, matching production behaviour.
    """
    async with engine.begin() as conn:
        await conn.execute(text(
            "DO $$ BEGIN CREATE ROLE corpmind_test NOINHERIT; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        ))
        await conn.execute(text("GRANT USAGE ON SCHEMA public TO corpmind_test"))
        await conn.execute(text(
            "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO corpmind_test"
        ))
        await conn.execute(text(
            "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO corpmind_test"
        ))


# ── Database fixtures (testcontainers) ────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Start a Postgres testcontainer and yield a connected engine."""
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            url = pg.get_connection_url().replace("psycopg2", "asyncpg")
            engine = create_async_engine(url, echo=False)

            # Run migrations in a thread — Alembic's env.py calls asyncio.run()
            # which raises RuntimeError if an event loop is already running
            # (pytest-asyncio owns this thread's loop). A worker thread has no
            # running loop so asyncio.run() inside env.py succeeds there.
            await asyncio.to_thread(_run_alembic_upgrade, url)
            await _setup_test_role(engine)

            yield engine
            await engine.dispose()
    except ImportError:
        pytest.skip("testcontainers not available")


@pytest_asyncio.fixture(scope="session")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    # Session-scoped to stay in the same event loop as db_engine.
    # Tests are isolated by UUID uniqueness, not by per-test rollback.
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        # Run as a non-superuser so PostgreSQL enforces RLS policies.
        await session.execute(text("SET ROLE corpmind_test"))
        yield session
        await session.rollback()


# ── HTTP client fixture ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    from corpmind.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── Feature flag helpers ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_feature_flags():
    from corpmind.core.flags import clear_overrides
    yield
    clear_overrides()
