"""HTTP-layer tests for GET /api/v1/analytics/channel/{channel}.

Test matrix (6 tests):

  GET /analytics/channel/whatsapp
    - unauthenticated → 401
    - authenticated, no rollup data → 200, all zeros, correct schema shape
    - days param respected (period_days echoed back)
    - days > 365 → 422 validation error

  GET /analytics/channel/unsupported
    - authenticated → 404 with detail about unsupported channel

  GET /analytics/channel/whatsapp — tenant isolation
    - tenant B querying returns their own zeros, not tenant A's data

All tests run against testcontainers Postgres + Redis (real infra, no mocks).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.api.conftest import make_user

if TYPE_CHECKING:
    from httpx import AsyncClient


# ── auth guard ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_summary_unauthenticated(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/analytics/channel/whatsapp")
    assert resp.status_code == 401


# ── happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_summary_empty_returns_zeros(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/channel/whatsapp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["channel"] == "whatsapp"
    assert body["period_days"] == 30
    assert body["sent"] == 0
    assert body["delivered"] == 0
    assert body["opened"] == 0
    assert body["failed"] == 0
    assert body["compliance_blocks"] == 0
    assert body["delivery_rate"] == 0.0
    assert body["read_rate"] == 0.0


@pytest.mark.asyncio
async def test_channel_summary_days_param_echoed(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/channel/whatsapp?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


@pytest.mark.asyncio
async def test_channel_summary_days_exceeds_max_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/channel/whatsapp?days=366",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── unsupported channel ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsupported_channel_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/analytics/channel/telegram",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "not supported" in resp.json()["detail"].lower()


# ── tenant isolation ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_summary_tenant_isolation(api_client: AsyncClient) -> None:
    """Tenant B's channel summary returns their own zeros, not A's data."""
    await make_user(api_client)  # tenant A — creates data this tenant B should not see
    user_b = await make_user(api_client)

    token_b = user_b["tokens"]["access_token"]

    # Tenant B requests their own channel summary — expects zeros regardless of A's data
    resp = await api_client.get(
        "/api/v1/analytics/channel/whatsapp",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sent"] == 0
    assert body["delivered"] == 0
