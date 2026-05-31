"""HTTP-layer tests for /api/v1/crm/*.

Test matrix (30 tests):

  POST /
    - success → 201, LeadOut shape, stage=discovered
    - duplicate active contact → 409 conflict
    - unauthenticated → 401
    - missing required fields → 422

  GET /
    - empty list for fresh workspace → 200, items=[], total=0
    - returns created lead → 200, 1 item
    - filter by valid stage → correct subset
    - unauthenticated → 401

  GET /{lead_id}
    - existing → 200, correct id + shape
    - not found → 404
    - unauthenticated → 401

  State machine — advance
    - discovered → engaged (200, correct from/to)
    - engaged → meeting_scheduled
    - meeting_scheduled → meeting_completed
    - meeting_completed → booked (booked_at populated)
    - advance terminal stage → 409

  Lost
    - mark discovered lead lost → 200, stage=lost
    - mark lost lead again → 409

  Score
    - valid score update → 200, score persisted
    - score > 100 → 422
    - score < 0 → 422

  Notes
    - update notes → 200, notes persisted
    - empty notes string → 422 (min_length=1)

  Meeting
    - advance to meeting_scheduled then set meeting_at → 200
    - set meeting_at on wrong stage → 409

  Stats
    - empty workspace → 200, all stage counts = 0
    - after creating leads → stage counts reflect data

  Tenant isolation
    - tenant B GET /{id} returns 404 for tenant A's lead
    - tenant B list does not include tenant A's leads
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.api.conftest import make_user


# ── Helpers ────────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    """Decode a JWT payload (no signature verification) to get org_id / workspace_id."""
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def _make_lead(
    client: AsyncClient,
    token: str,
    *,
    contact_id: str | None = None,
    workspace_id: str | None = None,
    score: int = 0,
    notes: str | None = None,
) -> dict:
    """POST /crm/ to create a lead in 'discovered' stage. Returns the response body."""
    claims = _claims(token)
    resp = await client.post(
        "/api/v1/crm/",
        json={
            "contact_id": contact_id or str(uuid.uuid4()),
            "workspace_id": workspace_id or claims["workspace_id"],
            "score": score,
            "notes": notes,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, f"_make_lead failed: {resp.text}"
    return resp.json()


async def _advance(client: AsyncClient, token: str, lead_id: str) -> dict:
    """POST /{lead_id}/advance and return the StageAdvanceResponse body."""
    resp = await client.post(
        f"/api/v1/crm/{lead_id}/advance",
        json={},
        headers=_auth(token),
    )
    assert resp.status_code == 200, f"_advance failed: {resp.text}"
    return resp.json()


async def _advance_to_meeting_scheduled(
    client: AsyncClient, token: str
) -> str:
    """Create a lead and advance it twice: discovered → engaged → meeting_scheduled.
    Returns the lead_id as a string.
    """
    lead = await _make_lead(client, token)
    lead_id = lead["id"]
    await _advance(client, token, lead_id)  # → engaged
    await _advance(client, token, lead_id)  # → meeting_scheduled
    return lead_id


# ── POST / ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_lead_success(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = str(uuid.uuid4())
    resp = await api_client.post(
        "/api/v1/crm/",
        json={
            "contact_id": contact_id,
            "workspace_id": claims["workspace_id"],
        },
        headers=_auth(token),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["stage"] == "discovered"
    assert body["contact_id"] == contact_id
    assert body["workspace_id"] == claims["workspace_id"]
    assert body["score"] == 0
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body
    assert isinstance(body["extra"], dict)


@pytest.mark.asyncio
async def test_create_lead_duplicate_active_contact_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    contact_id = str(uuid.uuid4())
    payload = {
        "contact_id": contact_id,
        "workspace_id": claims["workspace_id"],
    }

    r1 = await api_client.post("/api/v1/crm/", json=payload, headers=_auth(token))
    assert r1.status_code == 201

    r2 = await api_client.post("/api/v1/crm/", json=payload, headers=_auth(token))
    assert r2.status_code == 409
    assert r2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_create_lead_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/crm/",
        json={"contact_id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_create_lead_missing_fields_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.post("/api/v1/crm/", json={}, headers=_auth(token))
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ── GET / ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_leads_empty_for_new_workspace(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    resp = await api_client.get(
        "/api/v1/crm/",
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
async def test_list_leads_returns_created_lead(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    created = await _make_lead(api_client, token)

    resp = await api_client.get(
        "/api/v1/crm/",
        params={"workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    ids = [item["id"] for item in body["items"]]
    assert created["id"] in ids


@pytest.mark.asyncio
async def test_list_leads_filter_by_stage(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    # Create two leads; advance one to engaged
    lead_a = await _make_lead(api_client, token)
    lead_b = await _make_lead(api_client, token)
    await _advance(api_client, token, lead_b["id"])

    resp = await api_client.get(
        "/api/v1/crm/",
        params={"workspace_id": claims["workspace_id"], "stage": "discovered"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert lead_a["id"] in ids
    assert lead_b["id"] not in ids


@pytest.mark.asyncio
async def test_list_leads_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(
        "/api/v1/crm/",
        params={"workspace_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /{lead_id} ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_lead_success(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    created = await _make_lead(api_client, token)
    lead_id = created["id"]

    resp = await api_client.get(f"/api/v1/crm/{lead_id}", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == lead_id
    assert body["stage"] == "discovered"


@pytest.mark.asyncio
async def test_get_lead_not_found_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    resp = await api_client.get(
        f"/api/v1/crm/{uuid.uuid4()}",
        headers=_auth(token),
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_get_lead_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/crm/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /{lead_id}/advance — state machine ────────────────────────────────────

@pytest.mark.asyncio
async def test_advance_discovered_to_engaged(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)
    lead_id = lead["id"]

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/advance",
        json={},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["lead_id"] == lead_id
    assert body["from_stage"] == "discovered"
    assert body["to_stage"] == "engaged"


@pytest.mark.asyncio
async def test_advance_engaged_to_meeting_scheduled(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)
    lead_id = lead["id"]
    await _advance(api_client, token, lead_id)  # → engaged

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/advance",
        json={},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert resp.json()["from_stage"] == "engaged"
    assert resp.json()["to_stage"] == "meeting_scheduled"


@pytest.mark.asyncio
async def test_advance_meeting_scheduled_to_meeting_completed(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead_id = await _advance_to_meeting_scheduled(api_client, token)

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/advance",
        json={},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert resp.json()["from_stage"] == "meeting_scheduled"
    assert resp.json()["to_stage"] == "meeting_completed"


@pytest.mark.asyncio
async def test_advance_meeting_completed_to_booked(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead_id = await _advance_to_meeting_scheduled(api_client, token)
    await _advance(api_client, token, lead_id)  # → meeting_completed

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/advance",
        json={},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["from_stage"] == "meeting_completed"
    assert body["to_stage"] == "booked"

    # Confirm booked_at was set
    get_resp = await api_client.get(f"/api/v1/crm/{lead_id}", headers=_auth(token))
    assert get_resp.json()["booked_at"] is not None


@pytest.mark.asyncio
async def test_advance_terminal_stage_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    # Walk all the way to booked
    lead_id = await _advance_to_meeting_scheduled(api_client, token)
    await _advance(api_client, token, lead_id)  # → meeting_completed
    await _advance(api_client, token, lead_id)  # → booked

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/advance",
        json={},
        headers=_auth(token),
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


# ── POST /{lead_id}/lost ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_lead_lost_from_discovered(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)
    lead_id = lead["id"]

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/lost",
        json={"notes": "Not a fit"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "lost"
    assert body["notes"] == "Not a fit"


@pytest.mark.asyncio
async def test_mark_lost_twice_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)
    lead_id = lead["id"]

    await api_client.post(
        f"/api/v1/crm/{lead_id}/lost", json={}, headers=_auth(token)
    )

    resp = await api_client.post(
        f"/api/v1/crm/{lead_id}/lost", json={}, headers=_auth(token)
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


# ── PATCH /{lead_id}/score ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_score_success(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)
    lead_id = lead["id"]

    resp = await api_client.patch(
        f"/api/v1/crm/{lead_id}/score",
        json={"score": 85},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert resp.json()["score"] == 85


@pytest.mark.asyncio
async def test_update_score_above_100_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)

    resp = await api_client.patch(
        f"/api/v1/crm/{lead['id']}/score",
        json={"score": 101},
        headers=_auth(token),
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_update_score_below_0_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)

    resp = await api_client.patch(
        f"/api/v1/crm/{lead['id']}/score",
        json={"score": -1},
        headers=_auth(token),
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ── PATCH /{lead_id}/notes ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_notes_success(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)
    lead_id = lead["id"]

    resp = await api_client.patch(
        f"/api/v1/crm/{lead_id}/notes",
        json={"notes": "High-value prospect — decision maker confirmed."},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert resp.json()["notes"] == "High-value prospect — decision maker confirmed."


@pytest.mark.asyncio
async def test_update_notes_empty_string_returns_422(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)

    resp = await api_client.patch(
        f"/api/v1/crm/{lead['id']}/notes",
        json={"notes": ""},
        headers=_auth(token),
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ── PATCH /{lead_id}/meeting ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_meeting_on_meeting_scheduled_stage(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead_id = await _advance_to_meeting_scheduled(api_client, token)
    meeting_time = "2026-07-15T10:00:00Z"

    resp = await api_client.patch(
        f"/api/v1/crm/{lead_id}/meeting",
        json={"meeting_at": meeting_time},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_scheduled_at"] is not None
    assert body["stage"] == "meeting_scheduled"


@pytest.mark.asyncio
async def test_schedule_meeting_wrong_stage_returns_409(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]

    lead = await _make_lead(api_client, token)  # stage=discovered

    resp = await api_client.patch(
        f"/api/v1/crm/{lead['id']}/meeting",
        json={"meeting_at": "2026-07-15T10:00:00Z"},
        headers=_auth(token),
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


# ── GET /stats ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_stats_empty_workspace(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    resp = await api_client.get(
        "/api/v1/crm/stats",
        params={"workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == claims["workspace_id"]
    assert body["total"] == 0
    stage_counts = {s["stage"]: s["count"] for s in body["stages"]}
    for stage in ("discovered", "engaged", "meeting_scheduled", "meeting_completed", "booked", "lost"):
        assert stage_counts.get(stage, 0) == 0


@pytest.mark.asyncio
async def test_pipeline_stats_reflects_lead_counts(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    # Create 2 discovered leads; advance 1 to engaged
    await _make_lead(api_client, token)
    lead_b = await _make_lead(api_client, token)
    await _advance(api_client, token, lead_b["id"])

    resp = await api_client.get(
        "/api/v1/crm/stats",
        params={"workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    stage_counts = {s["stage"]: s["count"] for s in body["stages"]}
    assert stage_counts["discovered"] == 1
    assert stage_counts["engaged"] == 1


# ── Tenant isolation ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_get_lead_cross_tenant_returns_404(
    api_client: AsyncClient,
) -> None:
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)
    token_a = user_a["tokens"]["access_token"]
    token_b = user_b["tokens"]["access_token"]

    lead_a = await _make_lead(api_client, token_a)

    resp = await api_client.get(
        f"/api/v1/crm/{lead_a['id']}",
        headers=_auth(token_b),
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_list_leads_cross_tenant_excluded(
    api_client: AsyncClient,
) -> None:
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)
    token_a = user_a["tokens"]["access_token"]
    token_b = user_b["tokens"]["access_token"]
    claims_b = _claims(token_b)

    await _make_lead(api_client, token_a)

    resp = await api_client.get(
        "/api/v1/crm/",
        params={"workspace_id": claims_b["workspace_id"]},
        headers=_auth(token_b),
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 0
