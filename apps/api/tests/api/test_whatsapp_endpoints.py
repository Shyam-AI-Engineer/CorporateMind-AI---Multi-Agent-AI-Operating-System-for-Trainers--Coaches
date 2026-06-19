"""API-layer tests for WhatsApp module endpoints.

Test matrix:

  GET /api/v1/whatsapp/templates
    - unauthenticated → 401
    - authenticated, no templates → 200, empty list

  POST /api/v1/whatsapp/webhook
    - no HMAC secret configured → 200 (dev mode, passes through)
    - valid HMAC, empty entry list → 200, processed=0
    - invalid HMAC → 401

  GET /api/v1/whatsapp/webhook (Meta challenge verification)
    - correct verify token → 200, returns challenge int
    - wrong verify token → 403
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user


# ── /templates ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_templates_unauthenticated(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/whatsapp/templates")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_templates_empty_returns_list(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    resp = await api_client.get(
        "/api/v1/whatsapp/templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 0
    assert isinstance(body["items"], list)


# ── /webhook POST ──────────────────────────────────────────────────────────────

def _sign_payload(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_empty_entries_ok(api_client: AsyncClient, monkeypatch) -> None:
    """Empty entry list → 200, no processing needed."""
    from corpmind.channels.registry import initialize_adapters
    initialize_adapters()
    monkeypatch.setattr(
        "corpmind.core.config.settings.WHATSAPP_WEBHOOK_SECRET", "", raising=False
    )
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [],
    }).encode()
    resp = await api_client.post(
        "/api/v1/whatsapp/webhook",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["processed"] == 0


@pytest.mark.asyncio
async def test_webhook_invalid_hmac_returns_401(api_client: AsyncClient, monkeypatch) -> None:
    from corpmind.channels.registry import initialize_adapters
    initialize_adapters()
    monkeypatch.setattr(
        "corpmind.core.config.settings.WHATSAPP_WEBHOOK_SECRET", "correct-secret", raising=False
    )
    payload = b'{"object":"whatsapp_business_account","entry":[]}'
    resp = await api_client.post(
        "/api/v1/whatsapp/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=wronghash",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_valid_hmac_accepted(api_client: AsyncClient, monkeypatch) -> None:
    from corpmind.channels.registry import initialize_adapters
    initialize_adapters()
    secret = "test-webhook-secret"
    monkeypatch.setattr(
        "corpmind.core.config.settings.WHATSAPP_WEBHOOK_SECRET", secret, raising=False
    )
    payload = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [],
    }).encode()
    sig = _sign_payload(payload, secret)
    resp = await api_client.post(
        "/api/v1/whatsapp/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200


# ── /webhook GET (Meta challenge) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_verify_correct_token(api_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "corpmind.core.config.settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN", "my-verify-token",
        raising=False,
    )
    resp = await api_client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my-verify-token",
            "hub.challenge": "12345",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == 12345


@pytest.mark.asyncio
async def test_webhook_verify_wrong_token_returns_403(
    api_client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "corpmind.core.config.settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN", "correct-token",
        raising=False,
    )
    resp = await api_client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "99999",
        },
    )
    assert resp.status_code == 403
