"""HTTP-layer tests for the booking webhook endpoint — Sprint 14.

POST /api/v1/webhooks/booking/{workspace_id}

Test matrix (11 tests):
  - Valid HMAC + booking.created → 200 {"status": "ok"}
  - Invalid HMAC signature → 401
  - Workspace not found (unknown UUID) → 200 (silent drop, no info leak)
  - Workspace with no secret configured → 200 (silent drop)
  - Invalid JSON body (HMAC passes) → 422 / domain error
  - Duplicate event (idempotency) → 200, second call short-circuits
  - Workspace secret endpoints: GET booking-webhook → 200 with has_secret
  - Regenerate secret → 200, new secret returned
  - GET booking-webhook unauthenticated → 401
  - Regenerate unauthenticated → 401
  - booking.cancelled event type → 200 (skipped, not an error)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user


# ── Helpers ────────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _booking_payload(
    *,
    event_type: str = "booking.created",
    provider_event_id: str | None = None,
) -> dict:
    return {
        "provider": "calendly",
        "provider_event_id": provider_event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "invitee_email": f"hr-{uuid.uuid4().hex[:6]}@example.com",
        "invitee_name": "Jane HR",
        "scheduled_at": "2026-08-01T10:00:00Z",
        "metadata": {},
    }


async def _setup_workspace_with_secret(
    client: AsyncClient,
) -> tuple[str, str, str]:
    """Register a user, regenerate booking webhook secret, return (token, ws_id, secret)."""
    import base64

    user = await make_user(client)
    token = user["tokens"]["access_token"]

    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    claims = json.loads(base64.urlsafe_b64decode(part))
    workspace_id = claims["workspace_id"]

    resp = await client.post(
        "/api/v1/identity/workspace/booking-webhook/regenerate",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    secret = resp.json()["secret"]
    return token, workspace_id, secret


# ── Webhook delivery tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_hmac_booking_created_returns_200(api_client: AsyncClient) -> None:
    _, workspace_id, secret = await _setup_workspace_with_secret(api_client)
    body = json.dumps(_booking_payload()).encode()

    resp = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Booking-Signature": _sign(body, secret),
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(api_client: AsyncClient) -> None:
    _, workspace_id, _ = await _setup_workspace_with_secret(api_client)
    body = json.dumps(_booking_payload()).encode()

    resp = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Booking-Signature": "deadbeefdeadbeef",
        },
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_workspace_returns_200_silent_drop(api_client: AsyncClient) -> None:
    """Unknown workspace_id must not leak 404 — returns 200 silently."""
    body = json.dumps(_booking_payload()).encode()

    resp = await api_client.post(
        f"/api/v1/webhooks/booking/{uuid.uuid4()}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Booking-Signature": "any",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_no_secret_configured_returns_200_silent_drop(
    api_client: AsyncClient,
) -> None:
    """Workspace that has never regenerated its secret gets a silent 200 drop."""
    import base64

    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    workspace_id = json.loads(base64.urlsafe_b64decode(part))["workspace_id"]

    body = json.dumps(_booking_payload()).encode()
    resp = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}",
        content=body,
        headers={"Content-Type": "application/json", "X-Booking-Signature": "any"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_invalid_json_body_returns_error(api_client: AsyncClient) -> None:
    """After HMAC passes, invalid JSON raises a domain error."""
    _, workspace_id, secret = await _setup_workspace_with_secret(api_client)
    body = b"not-json"

    resp = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Booking-Signature": _sign(body, secret),
        },
    )

    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_duplicate_event_returns_200(api_client: AsyncClient) -> None:
    """Second delivery of the same provider_event_id returns 200 (idempotency)."""
    _, workspace_id, secret = await _setup_workspace_with_secret(api_client)
    payload = _booking_payload(provider_event_id="evt-idempotency-test")
    body = json.dumps(payload).encode()
    sig = _sign(body, secret)
    headers = {"Content-Type": "application/json", "X-Booking-Signature": sig}

    r1 = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}", content=body, headers=headers
    )
    r2 = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}", content=body, headers=headers
    )

    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_booking_cancelled_event_type_returns_200(api_client: AsyncClient) -> None:
    """booking.cancelled is a valid payload — skipped silently, not an error."""
    _, workspace_id, secret = await _setup_workspace_with_secret(api_client)
    body = json.dumps(_booking_payload(event_type="booking.cancelled")).encode()

    resp = await api_client.post(
        f"/api/v1/webhooks/booking/{workspace_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Booking-Signature": _sign(body, secret),
        },
    )

    assert resp.status_code == 200


# ── Workspace booking-webhook settings endpoints ───────────────────────────────

@pytest.mark.asyncio
async def test_get_booking_webhook_unauthenticated_returns_401(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/v1/identity/workspace/booking-webhook")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_booking_webhook_returns_url_and_has_secret_false(
    api_client: AsyncClient,
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/identity/workspace/booking-webhook",
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "webhook_url" in body
    assert "/api/v1/webhooks/booking/" in body["webhook_url"]
    assert body["has_secret"] is False
    assert body["secret"] is None


@pytest.mark.asyncio
async def test_regenerate_secret_returns_new_secret(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.post(
        "/api/v1/identity/workspace/booking-webhook/regenerate",
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_secret"] is True
    assert body["secret"] is not None
    assert len(body["secret"]) >= 32


@pytest.mark.asyncio
async def test_regenerate_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/identity/workspace/booking-webhook/regenerate"
    )
    assert resp.status_code == 401
