"""HTTP-layer tests for /api/v1/campaigns/*.

Test matrix (22 tests):

  POST /campaigns
    - authenticated → 201, correct schema shape
    - invalid channel → 422 validation
    - unauthenticated → 401

  GET /campaigns
    - fresh workspace → 200, items=[], total=0
    - after creating a campaign → item appears in list
    - unauthenticated → 401

  GET /campaigns/{id}
    - own campaign → 200, all fields present
    - nonexistent id → 404
    - unauthenticated → 401

  POST /campaigns/{id}/recipients
    - valid contactable contacts → 200, added_count and total_recipients
    - add to a locked campaign → 409 conflict
    - unauthenticated → 401

  GET /campaigns/{id}/recipients
    - after adding → 200, non-empty list with correct shape

  DELETE /campaigns/{id}/recipients/{contact_id}
    - existing recipient in draft → 204

  POST /campaigns/{id}/lock
    - draft with recipients → 200, status=locked, recipient_count updated
    - draft with no recipients → 422 validation
    - already-locked campaign → 409 conflict
    - unauthenticated → 401

  POST /campaigns/{id}/launch
    - locked campaign + locked trainer profile → 200, status=running (Celery mocked)
    - draft campaign → 409 (must lock first)
    - unauthenticated → 401

  PATCH /campaigns/{id}/status
    - pause a running campaign → 204
    - resume a paused campaign → 204 (Celery mocked)
    - cancel a draft campaign → 204
    - cancel an already-cancelled campaign → 409
    - unauthenticated → 401

  POST /campaigns/{id}/approve
    - approve a non-pending_hitl campaign → 409

  Tenant isolation
    - tenant A campaign returns 404 when tenant B requests it
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.api.conftest import make_user


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    """Decode JWT payload without signature verification."""
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def _seed_contact(engine: AsyncEngine, tenant_id: str) -> str:
    """Insert a contactable HR contact. Returns the contact UUID as str.

    Uses NullPool so each call gets a brand-new connection that the shared
    pool's SET ROLE corpmind_test has never touched.  The row carries the
    correct tenant_id so RLS-enforced request sessions can see it.
    """
    contact_id = str(uuid.uuid4())
    seed = create_async_engine(engine.url.render_as_string(hide_password=False), poolclass=NullPool)
    try:
        async with seed.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO hr_contacts"
                    " (id, tenant_id, company_id, full_name, source, source_type,"
                    "  email_deliverable, is_contactable)"
                    " VALUES (:id, :tid, :cid, 'Test Contact', 'test', 'webinar_registration',"
                    "         TRUE, TRUE)"
                ),
                {"id": contact_id, "tid": tenant_id, "cid": str(uuid.uuid4())},
            )
    finally:
        await seed.dispose()
    return contact_id


async def _seed_locked_profile(
    engine: AsyncEngine, workspace_id: str, tenant_id: str
) -> None:
    """Insert a locked trainer profile required for campaign launch."""
    seed = create_async_engine(engine.url.render_as_string(hide_password=False), poolclass=NullPool)
    try:
        async with seed.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO trainer_profiles"
                    " (id, tenant_id, workspace_id, topics, target_industries,"
                    "  languages, extraction_metadata, is_locked)"
                    " VALUES (:id, :tid, :wid,"
                    "         ARRAY[]::text[], ARRAY[]::text[], ARRAY[]::text[],"
                    "         '{}'::jsonb, TRUE)"
                ),
                {"id": str(uuid.uuid4()), "tid": tenant_id, "wid": workspace_id},
            )
    finally:
        await seed.dispose()


async def _make_campaign(
    client: AsyncClient,
    token: str,
    *,
    name: str = "Test Campaign",
    channel: str = "email",
) -> dict:
    """POST /campaigns and return the 201 response body."""
    resp = await client.post(
        "/api/v1/campaigns/",
        json={"name": name, "channel": channel},
        headers=_auth(token),
    )
    assert resp.status_code == 201, f"_make_campaign failed: {resp.text}"
    return resp.json()


async def _make_locked_campaign(
    client: AsyncClient, engine: AsyncEngine, token: str
) -> str:
    """Create a draft campaign with one recipient and lock it. Returns campaign_id."""
    claims = _claims(token)
    contact_id = await _seed_contact(engine, claims["org_id"])
    body = await _make_campaign(client, token)
    campaign_id = body["id"]

    resp = await client.post(
        f"/api/v1/campaigns/{campaign_id}/recipients",
        json={"contact_ids": [contact_id]},
        headers=_auth(token),
    )
    assert resp.status_code == 200

    resp = await client.post(f"/api/v1/campaigns/{campaign_id}/lock", headers=_auth(token))
    assert resp.status_code == 200

    return campaign_id


async def _make_running_campaign(
    client: AsyncClient, engine: AsyncEngine, token: str
) -> str:
    """Create, lock, and launch a campaign (Celery mocked). Returns campaign_id."""
    claims = _claims(token)
    await _seed_locked_profile(engine, claims["workspace_id"], claims["org_id"])
    campaign_id = await _make_locked_campaign(client, engine, token)

    with patch("corpmind.workers.tasks.campaigns.launch_campaign") as mock_task:
        mock_task.apply_async.return_value = None
        resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/launch", headers=_auth(token)
        )
    assert resp.status_code == 200

    return campaign_id


# ── POST /campaigns ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_campaign_returns_201(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.post(
        "/api/v1/campaigns/",
        json={"name": "Q3 Outreach", "channel": "email"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Q3 Outreach"
    assert body["channel"] == "email"
    assert body["status"] == "draft"
    assert body["recipient_count"] == 0
    assert "id" in body
    assert "workspace_id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_campaign_invalid_channel_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.post(
        "/api/v1/campaigns/",
        json={"name": "Bad Channel", "channel": "carrier_pigeon"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_create_campaign_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/campaigns/",
        json={"name": "No Auth", "channel": "email"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /campaigns ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_campaigns_empty_workspace(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    resp = await api_client.get(
        "/api/v1/campaigns/",
        params={"workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 50
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_campaigns_returns_created_campaign(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    await _make_campaign(api_client, token, name="Listed Campaign")

    resp = await api_client.get(
        "/api/v1/campaigns/",
        params={"workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    names = [c["name"] for c in body["items"]]
    assert "Listed Campaign" in names


@pytest.mark.asyncio
async def test_list_campaigns_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/campaigns/", params={"workspace_id": str(uuid.uuid4())})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /campaigns/{id} ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_campaign_returns_correct_shape(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    created = await _make_campaign(api_client, token)

    resp = await api_client.get(
        f"/api/v1/campaigns/{created['id']}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["name"] == created["name"]
    assert body["status"] == "draft"
    assert body["channel"] == "email"
    assert "workspace_id" in body


@pytest.mark.asyncio
async def test_get_campaign_not_found_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}",
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_campaign_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/campaigns/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Recipient management ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_recipients_returns_counts(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    body = await _make_campaign(api_client, token)
    campaign_id = body["id"]

    resp = await api_client.post(
        f"/api/v1/campaigns/{campaign_id}/recipients",
        json={"contact_ids": [contact_id]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["added_count"] == 1
    assert result["total_recipients"] == 1


@pytest.mark.asyncio
async def test_add_recipients_to_locked_campaign_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    campaign_id = await _make_locked_campaign(api_client, db_engine, token)

    # Try to add another contact to the now-locked campaign
    extra_contact = await _seed_contact(db_engine, claims["org_id"])
    resp = await api_client.post(
        f"/api/v1/campaigns/{campaign_id}/recipients",
        json={"contact_ids": [extra_contact]},
        headers=_auth(token),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_add_recipients_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        f"/api/v1/campaigns/{uuid.uuid4()}/recipients",
        json={"contact_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_list_recipients_returns_added_contacts(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    body = await _make_campaign(api_client, token)
    campaign_id = body["id"]

    await api_client.post(
        f"/api/v1/campaigns/{campaign_id}/recipients",
        json={"contact_ids": [contact_id]},
        headers=_auth(token),
    )

    resp = await api_client.get(
        f"/api/v1/campaigns/{campaign_id}/recipients",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    recipients = resp.json()
    assert len(recipients) == 1
    assert recipients[0]["contact_id"] == contact_id
    assert recipients[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_remove_recipient_from_draft(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = await _seed_contact(db_engine, claims["org_id"])
    body = await _make_campaign(api_client, token)
    campaign_id = body["id"]

    await api_client.post(
        f"/api/v1/campaigns/{campaign_id}/recipients",
        json={"contact_ids": [contact_id]},
        headers=_auth(token),
    )

    resp = await api_client.delete(
        f"/api/v1/campaigns/{campaign_id}/recipients/{contact_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 204

    # Confirm removal
    resp = await api_client.get(
        f"/api/v1/campaigns/{campaign_id}/recipients", headers=_auth(token)
    )
    assert resp.json() == []


# ── Lock ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_campaign_transitions_to_locked(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    campaign_id = await _make_locked_campaign(api_client, db_engine, token)

    resp = await api_client.get(
        f"/api/v1/campaigns/{campaign_id}", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "locked"
    assert body["recipient_count"] == 1


@pytest.mark.asyncio
async def test_lock_empty_campaign_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    body = await _make_campaign(api_client, token)

    resp = await api_client.post(
        f"/api/v1/campaigns/{body['id']}/lock", headers=_auth(token)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_lock_already_locked_campaign_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    campaign_id = await _make_locked_campaign(api_client, db_engine, token)

    # Attempt to lock again
    resp = await api_client.post(
        f"/api/v1/campaigns/{campaign_id}/lock", headers=_auth(token)
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_lock_campaign_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"/api/v1/campaigns/{uuid.uuid4()}/lock")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Launch ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_launch_locked_campaign_returns_running(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    await _seed_locked_profile(db_engine, claims["workspace_id"], claims["org_id"])
    campaign_id = await _make_locked_campaign(api_client, db_engine, token)

    with patch("corpmind.workers.tasks.campaigns.launch_campaign") as mock_task:
        mock_task.apply_async.return_value = None
        resp = await api_client.post(
            f"/api/v1/campaigns/{campaign_id}/launch", headers=_auth(token)
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["hitl_required"] is False
    assert body["recipient_count"] == 1
    assert body["campaign_id"] == campaign_id
    mock_task.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_launch_draft_campaign_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    body = await _make_campaign(api_client, token)

    resp = await api_client.post(
        f"/api/v1/campaigns/{body['id']}/launch", headers=_auth(token)
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_launch_campaign_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"/api/v1/campaigns/{uuid.uuid4()}/launch")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Pause / Resume / Cancel ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pause_running_campaign_returns_204(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    campaign_id = await _make_running_campaign(api_client, db_engine, token)

    resp = await api_client.patch(
        f"/api/v1/campaigns/{campaign_id}/status",
        json={"status": "paused"},
        headers=_auth(token),
    )
    assert resp.status_code == 204

    # Status confirmed via GET
    resp = await api_client.get(
        f"/api/v1/campaigns/{campaign_id}", headers=_auth(token)
    )
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_resume_paused_campaign_returns_204(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    campaign_id = await _make_running_campaign(api_client, db_engine, token)

    # Pause first
    await api_client.patch(
        f"/api/v1/campaigns/{campaign_id}/status",
        json={"status": "paused"},
        headers=_auth(token),
    )

    with patch("corpmind.workers.tasks.campaigns.launch_campaign") as mock_task:
        mock_task.apply_async.return_value = None
        resp = await api_client.patch(
            f"/api/v1/campaigns/{campaign_id}/status",
            json={"status": "resumed"},
            headers=_auth(token),
        )

    assert resp.status_code == 204
    mock_task.apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_draft_campaign_returns_204(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    body = await _make_campaign(api_client, token)

    resp = await api_client.patch(
        f"/api/v1/campaigns/{body['id']}/status",
        json={"status": "cancelled"},
        headers=_auth(token),
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    body = await _make_campaign(api_client, token)
    campaign_id = body["id"]

    # First cancel succeeds
    await api_client.patch(
        f"/api/v1/campaigns/{campaign_id}/status",
        json={"status": "cancelled"},
        headers=_auth(token),
    )

    # Second cancel: already in terminal state
    resp = await api_client.patch(
        f"/api/v1/campaigns/{campaign_id}/status",
        json={"status": "cancelled"},
        headers=_auth(token),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_status_update_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.patch(
        f"/api/v1/campaigns/{uuid.uuid4()}/status",
        json={"status": "cancelled"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Approve ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_non_hitl_campaign_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    body = await _make_campaign(api_client, token)

    resp = await api_client.post(
        f"/api/v1/campaigns/{body['id']}/approve",
        headers=_auth(token),
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


# ── Tenant isolation ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_tenant_isolation(api_client: AsyncClient) -> None:
    """A campaign created by tenant A is invisible to tenant B.

    With TenantContext + PostgreSQL RLS, every authenticated request scopes its
    DB session to the requesting tenant's org_id.  A query for a foreign
    campaign_id returns no rows, causing the service to raise NotFoundError → 404.
    """
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    token_a = user_a["tokens"]["access_token"]
    token_b = user_b["tokens"]["access_token"]

    # Tenant A creates a campaign
    campaign_a = await _make_campaign(api_client, token_a, name="Tenant A Campaign")
    campaign_id = campaign_a["id"]

    # Tenant B tries to read it — must get 404, not the campaign data
    resp = await api_client.get(
        f"/api/v1/campaigns/{campaign_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 404, (
        f"Tenant isolation failure: tenant B read tenant A's campaign {campaign_id!r}"
    )
