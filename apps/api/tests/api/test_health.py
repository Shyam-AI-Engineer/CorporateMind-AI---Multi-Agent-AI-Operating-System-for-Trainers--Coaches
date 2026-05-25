"""API health check tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_healthz_returns_ok(api_client) -> None:
    response = await api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
