"""Tenant isolation regression tests.

These tests create two tenants, write data into one, and assert the other
cannot read it via any query path. Required for every new table or query.
"""

from __future__ import annotations

import uuid

import pytest

from corpmind.core.tenancy import set_tenant_context
from corpmind.modules.campaigns.models import Campaign
from corpmind.modules.campaigns.repo import CampaignRepo


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
