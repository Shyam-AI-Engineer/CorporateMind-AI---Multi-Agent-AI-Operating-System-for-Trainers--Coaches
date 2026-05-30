"""Tenant isolation regression tests.

Two layers of protection are verified here:

  1. App-layer isolation  — ORM / repo queries always filter by tenant_id.
     These tests would catch bugs where the application accidentally omits
     a WHERE clause but the DB has no RLS to catch it.

  2. DB-layer isolation (RLS) — PostgreSQL policies enforce the same filter
     even when the app issues raw SQL.  These tests verify the policies
     installed by migration f5a3c8d92e1b behave correctly:
       - Correct tenant context → rows visible.
       - Wrong tenant context   → rows invisible (USING policy).
       - No tenant context      → zero rows visible (fail-closed).
       - Wrong tenant INSERT    → rejected (WITH CHECK policy).

Required for every PR that adds a new table or new query path.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.campaigns.models import Campaign
from corpmind.modules.campaigns.repo import CampaignRepo
from corpmind.modules.trainer_intel.models import TrainerProfile
from corpmind.modules.trainer_intel.repo import TrainerProfileRepo


@pytest.mark.asyncio
async def test_campaign_isolation(db_session, tenant_a, tenant_b) -> None:
    """Campaigns written by tenant A are invisible to tenant B."""
    # Write data as tenant A
    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))

    campaign = Campaign(
        tenant_id=tenant_a.org_id,
        workspace_id=tenant_a.workspace_id,
        name="Tenant A Campaign",
        channel="email",
        created_by=tenant_a.user_id,
    )
    db_session.add(campaign)
    await db_session.flush()

    # Query as tenant B — must return nothing
    clear_tenant_context(token_a)

    token_b = set_tenant_context(tenant_b)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_b.org_id}'"))
    repo = CampaignRepo(db_session)
    result = await repo.find_by_id(campaign.id)
    assert result is None, "Tenant B must not see Tenant A's campaign"

    clear_tenant_context(token_b)


@pytest.mark.asyncio
async def test_trainer_profile_isolation(db_session, tenant_a, tenant_b) -> None:
    """TrainerProfile written by tenant A is invisible to tenant B via repo + ORM."""
    # ── Write as tenant A ─────────────────────────────────────────────────────
    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))

    profile = TrainerProfile(
        tenant_id=tenant_a.org_id,
        workspace_id=tenant_a.workspace_id,
        niche="Leadership coaching",
        topics=["Executive Presence", "Team Dynamics"],
        tone="authoritative",
        target_industries=["BFSI"],
        languages=["en"],
    )
    db_session.add(profile)
    await db_session.flush()
    a_profile_id = profile.id
    a_workspace_id = tenant_a.workspace_id

    clear_tenant_context(token_a)

    # ── Read as tenant B — must see nothing ───────────────────────────────────
    token_b = set_tenant_context(tenant_b)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_b.org_id}'"))

    repo = TrainerProfileRepo(db_session)

    # 1. find_for_workspace using A's workspace_id (B is querying with B's tenant filter)
    leaked = await repo.find_for_workspace(a_workspace_id)
    assert leaked is None, "Tenant B must not see Tenant A's profile via find_for_workspace"

    # 2. Defense-in-depth: direct SELECT under tenant B's RLS session var must also return 0
    rows = await db_session.execute(
        text("SELECT id FROM trainer_profiles WHERE id = :pid"),
        {"pid": str(a_profile_id)},
    )
    assert rows.first() is None, "RLS must block direct SELECT of cross-tenant row"

    clear_tenant_context(token_b)


# ── RLS policy-layer tests ────────────────────────────────────────────────────
# The tests above verify app-layer isolation.  The tests below probe the DB
# policies directly — they would catch a scenario where the app layer is
# bypassed (e.g. a future raw-SQL admin tool) but the DB policies hold.


@pytest.mark.asyncio
async def test_rls_correct_tenant_can_read_own_rows(db_session, tenant_a) -> None:
    """Owner can always read their own rows under RLS."""
    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))

    campaign = Campaign(
        tenant_id=tenant_a.org_id,
        workspace_id=tenant_a.workspace_id,
        name="Visible to A",
        channel="email",
        created_by=tenant_a.user_id,
    )
    db_session.add(campaign)
    await db_session.flush()

    rows = await db_session.execute(
        text("SELECT id FROM campaigns WHERE id = :cid"),
        {"cid": str(campaign.id)},
    )
    assert rows.first() is not None, "Tenant A must be able to read their own campaign"

    clear_tenant_context(token_a)


@pytest.mark.asyncio
async def test_rls_fail_closed_without_tenant_context(db_session, tenant_a) -> None:
    """When app.tenant_id is not set, RLS denies all rows (fail-closed).

    This validates the current_setting('app.tenant_id', true) expression:
    the 'true' flag returns NULL instead of raising, and NULL = tenant_id
    is always FALSE — so zero rows are visible.  Public sessions (login /
    register / refresh) are protected by this property.
    """
    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))

    campaign = Campaign(
        tenant_id=tenant_a.org_id,
        workspace_id=tenant_a.workspace_id,
        name="Should be invisible without context",
        channel="email",
        created_by=tenant_a.user_id,
    )
    db_session.add(campaign)
    await db_session.flush()
    campaign_id = campaign.id
    clear_tenant_context(token_a)

    # Unset the GUC — simulates a public/unauthenticated session.
    # RESET removes the session-level setting so current_setting returns NULL.
    await db_session.execute(text("RESET app.tenant_id"))

    rows = await db_session.execute(
        text("SELECT id FROM campaigns WHERE id = :cid"),
        {"cid": str(campaign_id)},
    )
    assert rows.first() is None, (
        "Without app.tenant_id set, RLS must return no rows (fail-closed)"
    )


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_raw_sql_select(db_session, tenant_a, tenant_b) -> None:
    """Direct raw SQL SELECT cannot cross tenant boundaries.

    Unlike the ORM test, this calls execute(text(...)) with no WHERE clause —
    pure DB-level enforcement.
    """
    # Write as A
    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))
    profile = TrainerProfile(
        tenant_id=tenant_a.org_id,
        workspace_id=tenant_a.workspace_id,
        niche="Raw SQL target",
        topics=["Test"],
        target_industries=[],
        languages=["en"],
    )
    db_session.add(profile)
    await db_session.flush()
    profile_id = profile.id
    clear_tenant_context(token_a)

    # Read with B's context — no WHERE, relying solely on RLS
    token_b = set_tenant_context(tenant_b)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_b.org_id}'"))

    rows = await db_session.execute(
        text("SELECT id FROM trainer_profiles WHERE id = :pid"),
        {"pid": str(profile_id)},
    )
    assert rows.first() is None, "RLS must filter out A's profile from B's raw SQL query"

    clear_tenant_context(token_b)


@pytest.mark.asyncio
async def test_rls_with_check_blocks_cross_tenant_insert(db_session, tenant_a, tenant_b) -> None:
    """WITH CHECK prevents inserting a row with a different tenant's tenant_id.

    Attack vector: app is connected as tenant A but tries to insert a row
    tagged with tenant_b.org_id.  The RLS WITH CHECK clause must reject this.
    """
    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))

    # Attempt to insert with B's tenant_id while A's GUC is active
    poisoned = Campaign(
        tenant_id=tenant_b.org_id,  # wrong tenant
        workspace_id=tenant_b.workspace_id,
        name="Poisoned cross-tenant row",
        channel="email",
        created_by=tenant_a.user_id,
    )
    db_session.add(poisoned)

    with pytest.raises(Exception, match=r"(?i)(policy|check|violat|permission)"):
        await db_session.flush()

    await db_session.rollback()
    clear_tenant_context(token_a)


@pytest.mark.asyncio
async def test_rls_audit_events_not_restricted(db_session, tenant_a, tenant_b) -> None:
    """audit_events intentionally has NO RLS policy — reads are unrestricted.

    The admin compliance panel must be able to query across all tenants.
    This test confirms the table was excluded from the f5a3c8d92e1b migration.
    """
    from corpmind.modules.compliance.models import AuditEvent

    token_a = set_tenant_context(tenant_a)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"))

    event = AuditEvent(
        tenant_id=tenant_a.org_id,
        event_type="test_event",
        actor_id=tenant_a.user_id,
        channel="email",
        outcome="allowed",
        details={},
    )
    db_session.add(event)
    await db_session.flush()
    event_id = event.id
    clear_tenant_context(token_a)

    # Switch to B's context — audit_events has no RLS, so cross-tenant reads succeed
    token_b = set_tenant_context(tenant_b)
    await db_session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_b.org_id}'"))

    rows = await db_session.execute(
        text("SELECT id FROM audit_events WHERE id = :eid"),
        {"eid": str(event_id)},
    )
    assert rows.first() is not None, (
        "audit_events must remain cross-tenant readable (no RLS policy applied)"
    )

    clear_tenant_context(token_b)
