"""Repo-layer tests for AnalyticsDailyRepo against real Postgres.

Covers:
  upsert_rollup
    - first call → row created
    - second call with same (tenant, date, channel) → upserts, no duplicate
    - updated values overwrite prior values

  list_by_date_range
    - returns rows in date range, ordered desc
    - tenant isolation: tenant B cannot read tenant A's rows
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.analytics.repo import AnalyticsDailyRepo


TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def _ctx(tenant_id: uuid.UUID) -> TenantContext:
    return TenantContext(
        org_id=tenant_id,
        workspace_id=tenant_id,
        user_id=uuid.UUID(int=0),
        role="system",
        request_id=str(uuid.uuid4()),
    )


async def _set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))


# ── upsert_rollup ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_creates_row(db_session: AsyncSession) -> None:
    token = set_tenant_context(_ctx(TENANT_A))
    await _set_tenant(db_session, TENANT_A)
    try:
        repo = AnalyticsDailyRepo(db_session)
        await repo.upsert_rollup(
            tenant_id=TENANT_A,
            rollup_date=TODAY,
            channel=None,
            outreach_sent=10,
            outreach_delivered=8,
            outreach_opened=3,
            outreach_replied=2,
            compliance_blocks=0,
            meetings_scheduled=1,
            meetings_completed=0,
            leads_created=4,
            leads_booked=1,
            proposals_generated=2,
            proposals_approved=1,
            proposals_sent=1,
            ai_spend_inr=5.0,
        )
        await db_session.flush()

        rows = await repo.list_by_date_range(TODAY, TODAY)
        assert len(rows) == 1
        assert rows[0].outreach_sent == 10
        assert rows[0].leads_created == 4
        assert rows[0].proposals_generated == 2
    finally:
        clear_tenant_context(token)
        await db_session.rollback()


@pytest.mark.asyncio
async def test_upsert_idempotent_no_duplicate(db_session: AsyncSession) -> None:
    """Running upsert twice for the same (tenant, date, channel) → one row."""
    tid = uuid.uuid4()
    token = set_tenant_context(_ctx(tid))
    await _set_tenant(db_session, tid)
    try:
        repo = AnalyticsDailyRepo(db_session)
        base = dict(
            tenant_id=tid, rollup_date=TODAY, channel=None,
            outreach_sent=10, outreach_delivered=0, outreach_opened=0,
            outreach_replied=0, compliance_blocks=0, meetings_scheduled=0,
            meetings_completed=0, leads_created=0, leads_booked=0,
            proposals_generated=0, proposals_approved=0, proposals_sent=0,
            ai_spend_inr=0.0,
        )
        await repo.upsert_rollup(**base)
        await db_session.flush()

        # Second call with updated value
        base["outreach_sent"] = 99
        await repo.upsert_rollup(**base)
        await db_session.flush()

        rows = await repo.list_by_date_range(TODAY, TODAY)
        assert len(rows) == 1
        assert rows[0].outreach_sent == 99
    finally:
        clear_tenant_context(token)
        await db_session.rollback()


@pytest.mark.asyncio
async def test_list_by_date_range_ordered_desc(db_session: AsyncSession) -> None:
    tid = uuid.uuid4()
    token = set_tenant_context(_ctx(tid))
    await _set_tenant(db_session, tid)
    try:
        repo = AnalyticsDailyRepo(db_session)
        base = dict(
            tenant_id=tid, channel=None,
            outreach_sent=0, outreach_delivered=0, outreach_opened=0,
            outreach_replied=0, compliance_blocks=0, meetings_scheduled=0,
            meetings_completed=0, leads_created=0, leads_booked=0,
            proposals_generated=0, proposals_approved=0, proposals_sent=0,
            ai_spend_inr=0.0,
        )
        await repo.upsert_rollup(rollup_date=YESTERDAY, **base)
        await repo.upsert_rollup(rollup_date=TODAY, **base)
        await db_session.flush()

        rows = await repo.list_by_date_range(YESTERDAY, TODAY)
        assert len(rows) == 2
        assert rows[0].rollup_date == TODAY      # most recent first
        assert rows[1].rollup_date == YESTERDAY
    finally:
        clear_tenant_context(token)
        await db_session.rollback()


@pytest.mark.asyncio
async def test_tenant_isolation_list(db_session: AsyncSession) -> None:
    """Tenant B list_by_date_range must not return tenant A's rows."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()

    # Write as tenant A
    token_a = set_tenant_context(_ctx(tid_a))
    await _set_tenant(db_session, tid_a)
    try:
        repo_a = AnalyticsDailyRepo(db_session)
        await repo_a.upsert_rollup(
            tenant_id=tid_a, rollup_date=TODAY, channel=None,
            outreach_sent=77, outreach_delivered=0, outreach_opened=0,
            outreach_replied=0, compliance_blocks=0, meetings_scheduled=0,
            meetings_completed=0, leads_created=0, leads_booked=0,
            proposals_generated=0, proposals_approved=0, proposals_sent=0,
            ai_spend_inr=0.0,
        )
        await db_session.flush()
    finally:
        clear_tenant_context(token_a)

    # Read as tenant B — must see nothing
    token_b = set_tenant_context(_ctx(tid_b))
    await _set_tenant(db_session, tid_b)
    try:
        repo_b = AnalyticsDailyRepo(db_session)
        rows = await repo_b.list_by_date_range(TODAY, TODAY)
        assert all(r.tenant_id != tid_a for r in rows), (
            "Tenant B must not see tenant A's analytics rows"
        )
    finally:
        clear_tenant_context(token_b)
        await db_session.rollback()
