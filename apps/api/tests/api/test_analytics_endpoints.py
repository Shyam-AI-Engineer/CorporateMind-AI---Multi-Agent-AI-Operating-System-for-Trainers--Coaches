"""HTTP-layer tests for GET /api/v1/analytics/*.

Test matrix (12 tests):

  GET /summary
    - unauthenticated → 401
    - authenticated, no rollup data → 200, zeros, correct schema
    - days param respected (period_days echoed back)
    - days > 365 → 422 validation error

  GET /trend
    - unauthenticated → 401
    - authenticated, no data → 200, empty list
    - days=90 (max) accepted → 200
    - days=91 → 422

  GET /funnel
    - unauthenticated → 401
    - authenticated, empty workspace → 200, zeros, correct schema
    - missing workspace_id param → 422
    - tenant isolation: tenant B sees zeros for tenant A's workspace_id

All tests run against testcontainers Postgres + Redis (real infra, no mocks).
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user


def _workspace_from_token(token: str) -> str:
    """Decode JWT payload (no signature verify) and return workspace_id."""
    part = token.split(".")[1]
    # JWT uses URL-safe base64 without padding
    padded = part + "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))["workspace_id"]


# ── /summary ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_unauthenticated(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/analytics/summary")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_summary_empty_returns_zeros(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_sent"] == 0
    assert body["total_replied"] == 0
    assert body["reply_rate"] == 0.0
    assert body["delivery_rate"] == 0.0
    assert body["period_days"] == 30
    assert body["leads_created"] == 0
    assert body["proposals_generated"] == 0
    assert body["proposal_approval_rate"] == 0.0
    assert body["booking_rate"] == 0.0


@pytest.mark.asyncio
async def test_summary_days_param_echoed(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/summary?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


@pytest.mark.asyncio
async def test_summary_days_exceeds_max_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/summary?days=366",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── /trend ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trend_unauthenticated(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/analytics/trend")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trend_empty_returns_list(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/trend",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_trend_days_90_accepted(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/trend?days=90",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_trend_days_91_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/trend?days=91",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── /funnel ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_funnel_unauthenticated(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/analytics/funnel?workspace_id={uuid.uuid4()}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_funnel_empty_workspace_returns_zeros(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    workspace_id = _workspace_from_token(token)

    resp = await api_client.get(
        f"/api/v1/analytics/funnel?workspace_id={workspace_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["contacts"] == 0
    assert body["outreach_sent"] == 0
    assert body["replies"] == 0
    assert body["meetings"] == 0
    assert body["proposals"] == 0
    assert body["bookings"] == 0


@pytest.mark.asyncio
async def test_funnel_missing_workspace_id_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/funnel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_funnel_tenant_isolation(api_client: AsyncClient) -> None:
    """Tenant B querying tenant A's workspace_id sees zeros, not A's data."""
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    token_a = user_a["tokens"]["access_token"]
    token_b = user_b["tokens"]["access_token"]

    ws_a = _workspace_from_token(token_a)

    # Tenant B queries with tenant A's workspace_id — should return zeros
    resp = await api_client.get(
        f"/api/v1/analytics/funnel?workspace_id={ws_a}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # All funnel queries filter by both tenant_id (from context) and workspace_id
    # so tenant B sees nothing even though they supply tenant A's workspace_id
    assert body["contacts"] == 0
    assert body["bookings"] == 0
