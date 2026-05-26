"""Tenant isolation regression tests.

These tests create two tenants, write data into one, and assert the other
cannot read it via any query path. Required for every new table or query.
"""

from __future__ import annotations

import uuid  # noqa: F401  (kept for future tests)

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
    await db_session.execute(
        __import__("sqlalchemy", fromlist=["text"]).text(
            f"SET LOCAL app.tenant_id = '{tenant_a.org_id}'"
        )
    )

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
    from corpmind.core.tenancy import clear_tenant_context
    clear_tenant_context(token_a)

    token_b = set_tenant_context(tenant_b)
    await db_session.execute(
        __import__("sqlalchemy", fromlist=["text"]).text(
            f"SET LOCAL app.tenant_id = '{tenant_b.org_id}'"
        )
    )
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
