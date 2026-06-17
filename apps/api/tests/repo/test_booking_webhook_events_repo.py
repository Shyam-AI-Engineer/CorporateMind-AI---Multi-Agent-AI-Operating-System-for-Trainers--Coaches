"""Repo-layer tests for BookingWebhookEventRepo — Sprint 14.

Runs against a real Postgres testcontainer with RLS enforced.

Tenant isolation requirement (CLAUDE.md §Testing):
  Every PR that adds a new table must include a test that:
  1. Creates two tenants A and B.
  2. Writes data into A.
  3. As B, asserts the data is invisible to all read paths.

Tests (4):
  - reserve() returns a UUID on first call (inserted)
  - reserve() returns None on second call with same (provider, event_id) (duplicate)
  - mark_outcome() updates the outcome and lead_id columns
  - Tenant isolation: tenant B cannot read tenant A's booking_webhook_events row
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.crm.repo import BookingWebhookEventRepo
from tests.conftest import make_tenant_ctx


# ── Session helpers ────────────────────────────────────────────────────────────

async def _set_tenant(session: AsyncSession, org_id: uuid.UUID) -> None:
    await session.execute(text(f"SET LOCAL app.tenant_id = '{org_id}'"))


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reserve_returns_uuid_on_first_call(db_session: AsyncSession) -> None:
    ctx = make_tenant_ctx()
    await _set_tenant(db_session, ctx.org_id)

    repo = BookingWebhookEventRepo(db_session)
    event_id = await repo.reserve(
        tenant_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        provider="calendly",
        provider_event_id=f"evt-{uuid.uuid4()}",
        event_type="booking.created",
        invitee_email="hr@example.com",
        scheduled_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        raw_payload={"test": True},
    )

    assert isinstance(event_id, uuid.UUID)


@pytest.mark.asyncio
async def test_reserve_returns_none_on_duplicate(db_session: AsyncSession) -> None:
    ctx = make_tenant_ctx()
    await _set_tenant(db_session, ctx.org_id)

    repo = BookingWebhookEventRepo(db_session)
    provider_event_id = f"evt-dup-{uuid.uuid4()}"
    kwargs = dict(
        tenant_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        provider="cal_com",
        provider_event_id=provider_event_id,
        event_type="booking.created",
        invitee_email="hr@example.com",
        scheduled_at=None,
        raw_payload={},
    )

    first = await repo.reserve(**kwargs)
    second = await repo.reserve(**kwargs)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_mark_outcome_updates_row(db_session: AsyncSession) -> None:
    ctx = make_tenant_ctx()
    await _set_tenant(db_session, ctx.org_id)

    repo = BookingWebhookEventRepo(db_session)
    event_id = await repo.reserve(
        tenant_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        provider="tidycal",
        provider_event_id=f"evt-outcome-{uuid.uuid4()}",
        event_type="booking.created",
        invitee_email="test@example.com",
        scheduled_at=None,
        raw_payload={},
    )
    assert event_id is not None

    lead_id = uuid.uuid4()
    await repo.mark_outcome(event_id, outcome="applied", lead_id=lead_id)

    # Verify via find_by_provider_event
    row = await repo.find_by_provider_event(
        tenant_id=ctx.org_id,
        provider="tidycal",
        provider_event_id=event_id.hex,  # not what we need — use direct query
    )
    # find_by_provider_event uses provider_event_id string, not the row UUID.
    # Use a direct select instead.
    from sqlalchemy import select
    from corpmind.modules.crm.models import BookingWebhookEvent

    result = await db_session.execute(
        select(BookingWebhookEvent).where(BookingWebhookEvent.id == event_id)
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.outcome == "applied"
    assert record.lead_id == lead_id
    assert record.processed_at is not None


@pytest.mark.asyncio
async def test_tenant_isolation_cross_tenant_invisible(db_session: AsyncSession) -> None:
    """Tenant B cannot see Tenant A's booking_webhook_events rows."""
    ctx_a = make_tenant_ctx()
    ctx_b = make_tenant_ctx()

    # Write data as tenant A
    await _set_tenant(db_session, ctx_a.org_id)
    repo_a = BookingWebhookEventRepo(db_session)
    provider_event_id = f"evt-iso-{uuid.uuid4()}"
    event_id = await repo_a.reserve(
        tenant_id=ctx_a.org_id,
        workspace_id=ctx_a.workspace_id,
        provider="calendly",
        provider_event_id=provider_event_id,
        event_type="booking.created",
        invitee_email="secret@tenanta.com",
        scheduled_at=None,
        raw_payload={"secret": "tenant_a_data"},
    )
    assert event_id is not None
    await db_session.flush()

    # Switch to tenant B — RLS should hide tenant A's row
    await _set_tenant(db_session, ctx_b.org_id)
    row = await BookingWebhookEventRepo(db_session).find_by_provider_event(
        tenant_id=ctx_a.org_id,  # explicitly asking for A's data
        provider="calendly",
        provider_event_id=provider_event_id,
    )

    assert row is None, "RLS must prevent tenant B from reading tenant A's events"
