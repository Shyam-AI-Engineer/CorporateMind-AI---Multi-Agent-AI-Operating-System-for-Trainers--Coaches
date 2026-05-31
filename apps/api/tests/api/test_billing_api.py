"""HTTP-layer tests for /api/v1/billing/*.

Test matrix (7 tests):

  GET /billing/subscription
    - authenticated → 200, starter plan shape validated
    - unauthenticated → 401

  GET /billing/usage
    - authenticated → 200, zeroed counters for a fresh tenant
    - unauthenticated → 401

  GET /billing/summary
    - authenticated → 200, contains both subscription and usage objects
    - unauthenticated → 401

  Tenant isolation
    - two tenants see different subscription IDs (RLS + TenantContext)

Each test registers at least one fresh user via make_user() so:
  - The test gets a real Subscription + UsageMeter provisioned during /register.
  - Unique UUIDs in email/org_name guarantee tests are isolated despite sharing
    the session-scoped Postgres DB.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user


# ── GET /billing/subscription ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_subscription_returns_starter_plan(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_tier"] == "starter"
    assert body["status"] == "active"
    assert body["ai_budget_inr"] == 400.0
    assert body["ai_run_limit"] == 1000
    assert body["outreach_send_limit"] == 500
    assert "id" in body
    assert "current_period_start" in body
    assert "current_period_end" in body


@pytest.mark.asyncio
async def test_get_subscription_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/billing/subscription")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /billing/usage ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_usage_returns_zeroed_counters_for_fresh_tenant(
    api_client: AsyncClient,
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/billing/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # A brand-new tenant has consumed nothing yet
    assert body["ai_runs_used"] == 0
    assert body["outreach_sends_used"] == 0
    assert body["ai_spend_inr"] == 0.0
    assert body["budget_utilization_pct"] == 0.0
    # Limits reflect the starter tier provisioned during /register
    assert body["ai_runs_limit"] == 1000
    assert body["outreach_sends_limit"] == 500
    assert body["ai_budget_inr"] == 400.0


@pytest.mark.asyncio
async def test_get_usage_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/billing/usage")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /billing/summary ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_summary_returns_subscription_and_usage(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/billing/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "subscription" in body
    assert "usage" in body
    # Cross-check: subscription.id must be a valid UUID string
    assert len(body["subscription"]["id"]) == 36
    # Usage must be consistent with the subscription limits
    assert body["usage"]["ai_budget_inr"] == body["subscription"]["ai_budget_inr"]


@pytest.mark.asyncio
async def test_get_summary_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/billing/summary")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_billing_tenant_isolation(api_client: AsyncClient) -> None:
    """Tenant A and tenant B must never see each other's subscription.

    Both users get a Subscription provisioned during /register.  With the
    JWT-derived TenantContext and PostgreSQL RLS, each authenticated request
    can only see its own tenant's rows.  If RLS or TenantContext were broken,
    both queries would return the same subscription row, causing the ID check
    to fail.
    """
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    token_a = user_a["tokens"]["access_token"]
    token_b = user_b["tokens"]["access_token"]

    resp_a = await api_client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    resp_b = await api_client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    id_a = resp_a.json()["id"]
    id_b = resp_b.json()["id"]
    assert id_a != id_b, (
        f"Tenant isolation failure: both tenants received subscription {id_a!r}"
    )
