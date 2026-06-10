"""HTTP-layer tests for /api/v1/proposals/*.

Test matrix (16 tests):

  POST /proposals/
    - happy path: eligible lead → 201, status=draft, schema valid
    - ineligible stage (discovered) → 422
    - unknown lead_id → 404
    - unauthenticated → 401

  GET /proposals/
    - list returns items → 200, total ≥ 1
    - empty for unknown workspace → 200, total=0
    - pagination: offset > 0 returns later items
    - unauthenticated → 401

  GET /proposals/{id}
    - success → 200, full ProposalOut shape
    - not found → 404
    - unauthenticated → 401

  POST /proposals/{id}/send
    - transitions draft → sent → 200, status=sent
    - already sent → 409
    - unauthenticated → 401

  Tenant isolation
    - tenant B GET /{id} for tenant A's proposal → 404
    - tenant B GET / with tenant A's workspace_id → total=0

NOTE: Leads must be seeded via NullPool so the stage can be set directly to
'meeting_completed' without stepping through the CRM advance chain.
EuriClient.chat is patched at the class level to intercept the fresh
instantiation inside ProposalService.generate().
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.api.conftest import make_user

# ── Mock AI response ──────────────────────────────────────────────────────────

_PROPOSAL_CONTENT = {
    "title": "Leadership Excellence Workshop — Q3 2026",
    "executive_summary": (
        "Transform your leadership team with a tailored 2-day intensive programme "
        "addressing communication, influence, and executive presence."
    ),
    "proposed_training": {
        "topic": "Executive Communication & Influence",
        "duration": "2-day intensive workshop",
        "format": "in-person",
        "participants": "20–30 senior managers and directors",
    },
    "value_proposition": [
        "Measurably improved cross-functional collaboration",
        "Stronger executive presence across the leadership bench",
        "Reduced attrition in the senior IC and management layers",
    ],
    "proposed_agenda": [
        {"session": "Day 1 Morning", "focus": "Communication Foundations"},
        {"session": "Day 1 Afternoon", "focus": "Influence & Persuasion"},
        {"session": "Day 2 Morning", "focus": "Leadership Under Pressure"},
        {"session": "Day 2 Afternoon", "focus": "Practical Application & Action Plans"},
    ],
    "investment": "To be discussed based on participant count and customisation requirements.",
    "call_to_action": "Schedule a 30-minute discovery call to finalise the agenda and scope.",
}

_AI_RESPONSE = {"content": json.dumps(_PROPOSAL_CONTENT)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    """Decode JWT payload without signature verification."""
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def _seed_lead(
    engine: AsyncEngine,
    tenant_id: str,
    workspace_id: str,
    *,
    stage: str = "meeting_completed",
    score: int = 75,
    notes: str = "Met with HR Director — interested in leadership programme.",
) -> str:
    """Insert a leads row directly via NullPool and return its UUID.

    NullPool guarantees a fresh postgres-superuser connection so the insert
    bypasses RLS — the same pattern used by _seed_contact in outreach tests.
    Setting stage directly avoids the 3-step CRM advance chain in test setup.
    """
    lead_id = str(uuid.uuid4())
    seed = create_async_engine(
        engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed.begin() as conn:
            # Note: asyncpg does not support ::type casts on named parameters.
            # Use CAST(:param AS type) or a literal for the JSONB column.
            await conn.execute(
                text(
                    "INSERT INTO leads"
                    " (id, tenant_id, workspace_id, contact_id, stage, score, notes, extra)"
                    " VALUES (:id, :tid, :wid, :cid, :stage, :score, :notes, CAST(:extra AS jsonb))"
                ),
                {
                    "id": lead_id,
                    "tid": tenant_id,
                    "wid": workspace_id,
                    "cid": str(uuid.uuid4()),
                    "stage": stage,
                    "score": score,
                    "notes": notes,
                    "extra": "{}",
                },
            )
    finally:
        await seed.dispose()
    return lead_id


async def _generate_proposal(
    client: AsyncClient,
    token: str,
    lead_id: str,
    workspace_id: str,
) -> dict:
    """POST /proposals/ with mocked EuriClient; asserts 201 and returns body."""
    with patch(
        "corpmind.ai.euri_client.EuriClient.chat",
        new_callable=AsyncMock,
        return_value=_AI_RESPONSE,
    ):
        resp = await client.post(
            "/api/v1/proposals/",
            json={"lead_id": lead_id, "workspace_id": workspace_id},
            headers=_auth(token),
        )
    assert resp.status_code == 201, f"_generate_proposal failed: {resp.text}"
    return resp.json()


# ── POST /proposals/ ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_proposal_returns_201(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Happy path: eligible lead produces a 201 draft proposal with correct shape."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    body = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])

    assert "id" in body
    assert body["status"] == "draft"
    assert body["workspace_id"] == claims["workspace_id"]
    assert isinstance(body["content"], dict)
    assert body["content"]["title"] == _PROPOSAL_CONTENT["title"]
    assert body["sent_at"] is None
    assert "created_at" in body


@pytest.mark.asyncio
async def test_generate_proposal_booked_stage_returns_201(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """'booked' is also an eligible stage for proposal generation."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(
        db_engine, claims["org_id"], claims["workspace_id"], stage="booked"
    )
    body = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_generate_proposal_ineligible_stage_returns_422(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Lead in 'discovered' stage cannot have a proposal generated — 422."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(
        db_engine, claims["org_id"], claims["workspace_id"], stage="discovered"
    )
    resp = await api_client.post(
        "/api/v1/proposals/",
        json={"lead_id": lead_id, "workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_generate_proposal_unknown_lead_returns_404(
    api_client: AsyncClient,
) -> None:
    """Non-existent lead_id → 404."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    resp = await api_client.post(
        "/api/v1/proposals/",
        json={"lead_id": str(uuid.uuid4()), "workspace_id": claims["workspace_id"]},
        headers=_auth(token),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_generate_proposal_unauthenticated_returns_401(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v1/proposals/",
        json={"lead_id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /proposals/ ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_proposals_returns_200_with_items(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])

    resp = await api_client.get(
        f"/api/v1/proposals/?workspace_id={claims['workspace_id']}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1
    assert body["items"][0]["status"] == "draft"
    assert "limit" in body
    assert "offset" in body


@pytest.mark.asyncio
async def test_list_proposals_empty_for_unknown_workspace(
    api_client: AsyncClient,
) -> None:
    """An unknown workspace_id returns an empty list, not a 404."""
    user = await make_user(api_client)
    resp = await api_client.get(
        f"/api/v1/proposals/?workspace_id={uuid.uuid4()}",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_proposals_pagination(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """limit=1&offset=0 returns 1 item; limit=1&offset=1 returns the next item."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    # Generate 2 proposals
    for _ in range(2):
        lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
        await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])

    resp_p1 = await api_client.get(
        f"/api/v1/proposals/?workspace_id={claims['workspace_id']}&limit=1&offset=0",
        headers=_auth(token),
    )
    resp_p2 = await api_client.get(
        f"/api/v1/proposals/?workspace_id={claims['workspace_id']}&limit=1&offset=1",
        headers=_auth(token),
    )

    assert resp_p1.status_code == 200
    assert resp_p2.status_code == 200

    items_p1 = resp_p1.json()["items"]
    items_p2 = resp_p2.json()["items"]

    assert len(items_p1) == 1
    assert len(items_p2) == 1
    assert items_p1[0]["id"] != items_p2[0]["id"], "Pages must contain different proposals"


@pytest.mark.asyncio
async def test_list_proposals_unauthenticated_returns_401(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get(
        f"/api/v1/proposals/?workspace_id={uuid.uuid4()}"
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── GET /proposals/{id} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_proposal_returns_200(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp = await api_client.get(
        f"/api/v1/proposals/{proposal_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == proposal_id
    assert body["status"] == "draft"
    assert isinstance(body["content"], dict)
    assert "title" in body["content"]


@pytest.mark.asyncio
async def test_get_proposal_not_found_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    resp = await api_client.get(
        f"/api/v1/proposals/{uuid.uuid4()}",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_get_proposal_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/proposals/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /proposals/{id}/send ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_sent_transitions_draft_to_sent(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Marking a draft proposal as sent returns 200 with status='sent'."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/send",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == proposal_id
    assert body["status"] == "sent"
    assert body["sent_at"] is not None


@pytest.mark.asyncio
async def test_mark_sent_already_sent_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Calling send on an already-sent proposal returns 409 Conflict."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    # First send — succeeds
    resp1 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/send",
        headers=_auth(token),
    )
    assert resp1.status_code == 200

    # Second send — conflict
    resp2 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/send",
        headers=_auth(token),
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_mark_sent_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"/api/v1/proposals/{uuid.uuid4()}/send")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation_get_returns_404_for_other_tenant(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Tenant B calling GET /{id} for Tenant A's proposal receives 404."""
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    token_a = user_a["tokens"]["access_token"]
    claims_a = _claims(token_a)

    lead_id = await _seed_lead(db_engine, claims_a["org_id"], claims_a["workspace_id"])
    proposal = await _generate_proposal(
        api_client, token_a, lead_id, claims_a["workspace_id"]
    )
    proposal_id = proposal["id"]

    # Tenant B attempts to access tenant A's proposal
    resp = await api_client.get(
        f"/api/v1/proposals/{proposal_id}",
        headers=_auth(user_b["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_tenant_isolation_list_returns_empty_for_other_tenant(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Tenant B calling GET / with Tenant A's workspace_id returns total=0."""
    user_a = await make_user(api_client)
    user_b = await make_user(api_client)

    token_a = user_a["tokens"]["access_token"]
    claims_a = _claims(token_a)

    lead_id = await _seed_lead(db_engine, claims_a["org_id"], claims_a["workspace_id"])
    await _generate_proposal(api_client, token_a, lead_id, claims_a["workspace_id"])

    # Tenant B queries using tenant A's workspace_id
    resp = await api_client.get(
        f"/api/v1/proposals/?workspace_id={claims_a['workspace_id']}",
        headers=_auth(user_b["tokens"]["access_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0, "Tenant B must not see Tenant A's proposals"
    assert body["items"] == []
