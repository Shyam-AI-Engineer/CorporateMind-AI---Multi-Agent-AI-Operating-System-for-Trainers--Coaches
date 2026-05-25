"""Async SQLAlchemy engine, session factory, and base model.

Session lifecycle:
- FastAPI dependencies yield an AsyncSession per request.
- Celery tasks acquire sessions explicitly via `get_session()`.
- After acquiring a session, callers must call `set_rls_tenant()` to activate
  Postgres RLS for the connection — the repository base class does this automatically.
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from corpmind.core.config import settings

log = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    global _engine, _session_factory

    _engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=settings.APP_DEBUG,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    log.info("database.connected", url=settings.DATABASE_URL.split("@")[-1])


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
    log.info("database.disconnected")


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a tenant-scoped AsyncSession."""
    from corpmind.core.tenancy import get_tenant_context

    factory = get_session_factory()
    async with factory() as session:
        ctx = get_tenant_context()
        await set_rls_tenant(session, ctx.org_id)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def set_rls_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Activate Postgres RLS for the current transaction.

    Must be called BEFORE any query is issued on the session.
    RLS policy: USING (tenant_id = current_setting('app.tenant_id')::uuid)
    """
    await session.execute(
        text("SET LOCAL app.tenant_id = :tid"),
        {"tid": str(tenant_id)},
    )


# ── Declarative base ───────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """SQLAlchemy declarative base shared by all modules.

    All business tables inherit from TenantBase (below), which adds tenant_id.
    Tables that don't need RLS (e.g. audit_events, feature_flags) use Base directly.
    """


class TenantBase(Base):
    """Abstract base for every tenant-scoped business table.

    Adds tenant_id as the first column. Postgres RLS is applied on top.
    """

    __abstract__ = True

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Org-level tenant isolation key — must match app.tenant_id in RLS",
    )
