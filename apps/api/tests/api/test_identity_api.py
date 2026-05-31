"""HTTP-layer tests for /api/v1/identity/*.

Test matrix (13 tests):

  POST /register
    - success → 201, token shape, token_type=bearer
    - duplicate email → 409 conflict envelope
    - password too short (7 chars) → 422 validation
    - missing required fields → 422 validation

  POST /login
    - success → 200, token shape matches register
    - wrong password → 401 unauthenticated
    - unknown email → 401 unauthenticated
    - missing body → 422 validation

  POST /refresh
    - success → 200, new access + refresh tokens returned
    - token rotation: reuse old refresh token after rotation → 401
    - garbage refresh token string → 401

  GET /me
    - authenticated → 200, correct user fields in response
    - unauthenticated (no Authorization header) → 401
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import make_user


# ── /register ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/identity/register",
        json={
            "email": "alice@example.com",
            "password": "Str0ngP@ss!",
            "full_name": "Alice Trainer",
            "org_name": "Alice Academy",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int) and body["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(api_client: AsyncClient) -> None:
    payload = {
        "email": "dup@example.com",
        "password": "Str0ngP@ss!",
        "full_name": "Dup User",
        "org_name": "Dup Org",
    }
    r1 = await api_client.post("/api/v1/identity/register", json=payload)
    assert r1.status_code == 201

    r2 = await api_client.post("/api/v1/identity/register", json=payload)
    assert r2.status_code == 409
    assert r2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_register_short_password_returns_422(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/identity/register",
        json={
            "email": "short@example.com",
            "password": "abc1234",  # 7 chars — below min_length=8
            "full_name": "Short Pass",
            "org_name": "Short Org",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_register_missing_fields_returns_422(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/v1/identity/register", json={})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ── /login ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/identity/login",
        json={
            "email": user["payload"]["email"],
            "password": user["payload"]["password"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.post(
        "/api/v1/identity/login",
        json={"email": user["payload"]["email"], "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/identity/login",
        json={"email": "nobody@example.com", "password": "irrelevant"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_login_missing_body_returns_422(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/v1/identity/login", json={})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ── /refresh ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_success(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    old_refresh = user["tokens"]["refresh_token"]

    resp = await api_client.post(
        "/api/v1/identity/refresh",
        json={"refresh_token": old_refresh},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    # Token rotation: the refresh token jti must change on every use.
    # The access token may be byte-identical if both are issued within the
    # same second (RS256 is deterministic — same payload → same signature).
    assert body["refresh_token"] != old_refresh


@pytest.mark.asyncio
async def test_refresh_token_rotation_revokes_old_token(api_client: AsyncClient) -> None:
    """After a refresh, the old refresh token must be blocklisted."""
    user = await make_user(api_client)
    old_refresh = user["tokens"]["refresh_token"]

    # First refresh succeeds and rotates the token
    r1 = await api_client.post(
        "/api/v1/identity/refresh", json={"refresh_token": old_refresh}
    )
    assert r1.status_code == 200

    # Reusing the old (now revoked) refresh token must fail
    r2 = await api_client.post(
        "/api/v1/identity/refresh", json={"refresh_token": old_refresh}
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_refresh_garbage_token_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/identity/refresh",
        json={"refresh_token": "not.a.valid.jwt"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── /me ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_returns_authenticated_user(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    access_token = user["tokens"]["access_token"]

    resp = await api_client.get(
        "/api/v1/identity/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user["payload"]["email"]
    assert body["full_name"] == user["payload"]["full_name"]
    assert body["is_active"] is True
    assert "id" in body
    assert "org_id" in body


@pytest.mark.asyncio
async def test_me_without_auth_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/identity/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"
