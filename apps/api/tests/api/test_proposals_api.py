"""HTTP-layer tests for /api/v1/proposals/*.

Test matrix (27 tests):

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
    - approval_status filter: pending vs approved

  GET /proposals/{id}
    - success → 200, full ProposalOut shape (includes approval_status)
    - not found → 404
    - unauthenticated → 401

  POST /proposals/{id}/approve
    - happy path → 200, approval_status=approved
    - already approved → 409
    - not found → 404
    - unauthenticated → 401

  POST /proposals/{id}/reject
    - happy path → 200, approval_status=rejected, reason stored
    - empty reason → 422
    - already rejected → 409
    - unauthenticated → 401

  POST /proposals/{id}/send
    - approved draft → sent → 200, status=sent
    - pending_approval → 409 (not approved yet)
    - already sent → 409
    - unauthenticated → 401

  Tenant isolation
    - tenant B GET /{id} for tenant A's proposal → 404
    - tenant B GET / with tenant A's workspace_id → total=0

NOTE: Leads must be seeded via NullPool so the stage can be set directly to
'meeting_completed' without stepping through the CRM advance chain.
EuriClient.chat is patched at the class level to intercept the fresh
instantiation inside ProposalService.generate().
All registered users are OrgAdmin (identity service default), so approve/reject
happy-path tests work without special role setup.
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

from corpmind.modules.outreach.schemas import SendMessageResponse
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
    # Sprint 12A: approval fields present in every ProposalOut response
    assert body["approval_status"] == "pending_approval"
    assert body["approved_by"] is None
    assert body["approved_at"] is None
    assert body["rejected_reason"] is None


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


# ── POST /proposals/{id}/approve ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_proposal_returns_200(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """OrgAdmin can approve a pending proposal; response has approval_status=approved."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == proposal_id
    assert body["approval_status"] == "approved"
    assert body["approved_by"] is not None
    assert body["approved_at"] is not None
    assert body["status"] == "draft"  # delivery status unchanged


@pytest.mark.asyncio
async def test_approve_already_approved_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Approving an already-approved proposal returns 409."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp1 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        headers=_auth(token),
    )
    assert resp1.status_code == 200

    resp2 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/approve",
        headers=_auth(token),
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_approve_not_found_returns_404(api_client: AsyncClient) -> None:
    """Approving a non-existent proposal returns 404."""
    user = await make_user(api_client)
    resp = await api_client.post(
        f"/api/v1/proposals/{uuid.uuid4()}/approve",
        headers=_auth(user["tokens"]["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_approve_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"/api/v1/proposals/{uuid.uuid4()}/approve")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /proposals/{id}/reject ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_proposal_returns_200(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """OrgAdmin can reject a pending proposal; reason is stored in response."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"reason": "Scope does not align with Q3 budget constraints"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == proposal_id
    assert body["approval_status"] == "rejected"
    assert body["rejected_reason"] == "Scope does not align with Q3 budget constraints"


@pytest.mark.asyncio
async def test_reject_empty_reason_returns_422(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Rejection with blank reason fails schema validation — 422."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"reason": "   "},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reject_already_rejected_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Rejecting an already-rejected proposal returns 409."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    resp1 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"reason": "Initial rejection"},
        headers=_auth(token),
    )
    assert resp1.status_code == 200

    resp2 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/reject",
        json={"reason": "Duplicate rejection attempt"},
        headers=_auth(token),
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_reject_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        f"/api/v1/proposals/{uuid.uuid4()}/reject",
        json={"reason": "No auth"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


# ── POST /proposals/{id}/send ─────────────────────────────────────────────────
#
# deliver() requires a real contact email (hr_contacts) and SMTP for a full
# integration run.  The API tests patch both so the test stays fast and
# hermetic: _fetch_contact_email returns a synthetic email; OutreachService
# .send_message returns a queued SendMessageResponse without touching SMTP.
# The 409 guard tests need no patches — the guards fire before any SQL runs.

def _patch_deliver():
    """Context-manager stack that makes deliver() succeed without SMTP."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        with patch(
            "corpmind.modules.proposals.service.ProposalService._fetch_contact_email",
            new=AsyncMock(return_value="hr@example.com"),
        ):
            with patch(
                "corpmind.modules.outreach.service.OutreachService",
            ) as MockOS:
                MockOS.return_value.send_message = AsyncMock(
                    return_value=SendMessageResponse(
                        message_id=uuid.uuid4(), status="queued"
                    )
                )
                yield

    return _ctx()


@pytest.mark.asyncio
async def test_send_proposal_transitions_approved_draft_to_sent(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Approved draft → deliver() → 200; status=sent, delivery fields populated."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    await api_client.post(
        f"/api/v1/proposals/{proposal_id}/approve", headers=_auth(token)
    )

    async with _patch_deliver():
        send_resp = await api_client.post(
            f"/api/v1/proposals/{proposal_id}/send", headers=_auth(token)
        )

    assert send_resp.status_code == 200
    body = send_resp.json()
    assert body["id"] == proposal_id
    assert body["status"] == "sent"
    assert body["sent_at"] is not None
    assert body["approval_status"] == "approved"
    assert body["outbound_message_id"] is not None
    assert body["delivery_status"] == "queued"


@pytest.mark.asyncio
async def test_send_proposal_pending_approval_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Sending a proposal that has not been approved returns 409."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])

    resp = await api_client.post(
        f"/api/v1/proposals/{proposal['id']}/send", headers=_auth(token)
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_send_proposal_already_sent_returns_409(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Calling send twice on the same proposal returns 409 on the second call."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    await api_client.post(
        f"/api/v1/proposals/{proposal_id}/approve", headers=_auth(token)
    )

    async with _patch_deliver():
        resp1 = await api_client.post(
            f"/api/v1/proposals/{proposal_id}/send", headers=_auth(token)
        )
    assert resp1.status_code == 200

    # Second send — status is now 'sent'; guard fires immediately, no patches needed
    resp2 = await api_client.post(
        f"/api/v1/proposals/{proposal_id}/send", headers=_auth(token)
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_send_proposal_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.post(f"/api/v1/proposals/{uuid.uuid4()}/send")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_send_proposal_creates_outbound_message_row(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """After deliver(), a row exists in outbound_messages for the proposal's contact."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    lead_id = await _seed_lead(db_engine, claims["org_id"], claims["workspace_id"])
    proposal = await _generate_proposal(api_client, token, lead_id, claims["workspace_id"])
    proposal_id = proposal["id"]

    await api_client.post(
        f"/api/v1/proposals/{proposal_id}/approve", headers=_auth(token)
    )

    async with _patch_deliver():
        send_resp = await api_client.post(
            f"/api/v1/proposals/{proposal_id}/send", headers=_auth(token)
        )
    assert send_resp.status_code == 200
    outbound_id = send_resp.json()["outbound_message_id"]
    assert outbound_id is not None

    # Verify the row exists in the DB directly via NullPool (bypasses RLS for
    # the assertion query so we don't need a full tenant session setup here).
    seed = create_async_engine(
        db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed.begin() as conn:
            row = await conn.execute(
                text(
                    "SELECT id, channel, status FROM outbound_messages"
                    " WHERE id = :mid"
                ),
                {"mid": outbound_id},
            )
            found = row.one_or_none()
        assert found is not None, "OutboundMessage row must exist after deliver()"
        assert found[1] == "email"
        # Status is whatever OutreachService.send_message set — in the mock it
        # returns 'queued' but the mock bypasses the actual DB write for the
        # outbound_messages status column.  Assert the row exists, not its status.
    finally:
        await seed.dispose()


# ── GET /proposals/ (approval_status filter) ──────────────────────────────────

@pytest.mark.asyncio
async def test_list_filter_by_approval_status(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """approval_status=pending_approval filter returns only un-approved proposals."""
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)

    ws_id = claims["workspace_id"]

    # Generate two proposals
    lead_id_1 = await _seed_lead(db_engine, claims["org_id"], ws_id)
    proposal_1 = await _generate_proposal(api_client, token, lead_id_1, ws_id)

    lead_id_2 = await _seed_lead(db_engine, claims["org_id"], ws_id)
    proposal_2 = await _generate_proposal(api_client, token, lead_id_2, ws_id)

    # Approve only proposal_1
    await api_client.post(
        f"/api/v1/proposals/{proposal_1['id']}/approve",
        headers=_auth(token),
    )

    # Filter by pending_approval — should return only proposal_2
    resp = await api_client.get(
        f"/api/v1/proposals/?workspace_id={ws_id}&approval_status=pending_approval",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == proposal_2["id"]
    assert body["items"][0]["approval_status"] == "pending_approval"


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
