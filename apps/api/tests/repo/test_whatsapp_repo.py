"""Repo-layer tests for WhatsApp template + session repos.

Tests run against a real testcontainer Postgres instance (RLS enforced).
Pattern: call set_tenant_context() + SET LOCAL app.tenant_id before any
DB access — mirrors test_analytics_daily_repo.py convention.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.whatsapp.models import WhatsAppSession, WhatsAppTemplate
from corpmind.modules.whatsapp.repo import WhatsAppSessionRepo, WhatsAppTemplateRepo

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


def _ctx(tid: uuid.UUID) -> TenantContext:
    return TenantContext(
        org_id=tid,
        workspace_id=tid,
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )


async def _set_tenant(session: AsyncSession, tid: uuid.UUID) -> None:
    await session.execute(text(f"SET LOCAL app.tenant_id = '{tid}'"))


def _template(tid: uuid.UUID, *, approval_status: str = "approved") -> WhatsAppTemplate:
    return WhatsAppTemplate(
        tenant_id=tid,
        name="outreach_intro_v1",
        language="en",
        category="MARKETING",
        body="Hi there, let's connect!",
        approval_status=approval_status,
        components={},
    )


def _session_obj(tid: uuid.UUID, contact_id: uuid.UUID, *, active: bool = True) -> WhatsAppSession:
    now = datetime.now(UTC)
    expires = now + timedelta(hours=24) if active else now - timedelta(hours=1)
    return WhatsAppSession(
        tenant_id=tid,
        contact_id=contact_id,
        phone_number="+919876543210",
        window_opened_at=now - timedelta(hours=1),
        window_expires_at=expires,
        is_active=active,
    )


# ── WhatsAppTemplateRepo ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_approved_returns_only_approved(db_session: AsyncSession) -> None:
    tok = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        db_session.add(_template(TENANT_A, approval_status="approved"))
        db_session.add(_template(TENANT_A, approval_status="pending"))
        await db_session.flush()

        repo = WhatsAppTemplateRepo(db_session)
        templates = await repo.list_approved()
        assert len(templates) == 1
        assert templates[0].approval_status == "approved"
    finally:
        clear_tenant_context(tok)


@pytest.mark.asyncio
async def test_find_by_name_and_language(db_session: AsyncSession) -> None:
    tok = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        db_session.add(_template(TENANT_A))
        await db_session.flush()

        repo = WhatsAppTemplateRepo(db_session)
        found = await repo.find_by_name_and_language("outreach_intro_v1", "en")
        assert found is not None
        assert found.name == "outreach_intro_v1"
    finally:
        clear_tenant_context(tok)


@pytest.mark.asyncio
async def test_find_by_name_returns_none_for_wrong_language(db_session: AsyncSession) -> None:
    tok = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        db_session.add(_template(TENANT_A))
        await db_session.flush()

        repo = WhatsAppTemplateRepo(db_session)
        found = await repo.find_by_name_and_language("outreach_intro_v1", "hi")
        assert found is None
    finally:
        clear_tenant_context(tok)


# ── WhatsAppSessionRepo ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_active_session_returns_active(db_session: AsyncSession) -> None:
    cid = uuid.uuid4()
    tok = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        db_session.add(_session_obj(TENANT_A, cid, active=True))
        await db_session.flush()

        repo = WhatsAppSessionRepo(db_session)
        result = await repo.find_active_session(cid)
        assert result is not None
        assert result.contact_id == cid
    finally:
        clear_tenant_context(tok)


@pytest.mark.asyncio
async def test_find_active_session_returns_none_when_expired(db_session: AsyncSession) -> None:
    cid = uuid.uuid4()
    tok = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        db_session.add(_session_obj(TENANT_A, cid, active=False))
        await db_session.flush()

        repo = WhatsAppSessionRepo(db_session)
        result = await repo.find_active_session(cid)
        assert result is None
    finally:
        clear_tenant_context(tok)


@pytest.mark.asyncio
async def test_tenant_isolation_templates(db_session: AsyncSession) -> None:
    """Tenant B cannot see tenant A's templates."""
    tok_a = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        db_session.add(_template(TENANT_A))
        await db_session.flush()
    finally:
        clear_tenant_context(tok_a)

    tok_b = set_tenant_context(_ctx(TENANT_B))
    await _set_tenant(db_session, TENANT_B)
    try:
        repo = WhatsAppTemplateRepo(db_session)
        templates = await repo.list_approved()
        assert templates == []
    finally:
        clear_tenant_context(tok_b)
