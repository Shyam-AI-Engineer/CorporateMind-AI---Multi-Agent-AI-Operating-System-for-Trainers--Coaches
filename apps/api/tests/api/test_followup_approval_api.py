"""HTTP-layer tests for the Sprint 8C follow-up approval surface.

Routes under /api/v1/crm/follow-ups/{task_id}/{review,draft,approve,reject}.

A parked follow-up (status='awaiting_approval' + a draft outbound_messages row)
is seeded directly via NullPool (superuser, bypasses RLS) — the same pattern as
the proposals API tests.  OutreachService.send_message is patched at the class
level for the approve tests so the flow never touches Celery or the real
compliance gate; the approve→done / approve→blocked transitions and audit/
activity writes still run against the test Postgres.

Covers: review payload, edit, reject, approve (done + blocked), tenant isolation,
and the status guard (409 once a task leaves awaiting_approval).
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def _seed_parked_followup(
    engine: AsyncEngine, tenant_id: str, workspace_id: str
) -> tuple[str, str]:
    """Insert a draft outbound + an awaiting_approval follow_up_task (NullPool).

    Returns (task_id, draft_id).  source_outbound_message_id is left NULL so the
    approve path resolves a null threading anchor (no extra seeding needed), and
    no inbox row is seeded (review tolerates a missing reply).
    """
    task_id = str(uuid.uuid4())
    draft_id = str(uuid.uuid4())
    contact_id = str(uuid.uuid4())
    seed = create_async_engine(
        engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO outbound_messages"
                    " (id, tenant_id, contact_id, channel, subject, body,"
                    "  prompt_version, status)"
                    " VALUES (:id, :tid, :cid, 'email', :subj, :body,"
                    "  'outreach.followup.question.v1', 'draft')"
                ),
                {
                    "id": draft_id,
                    "tid": tenant_id,
                    "cid": contact_id,
                    "subj": "Re: Your question",
                    "body": "Thanks for asking — here is the answer.",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO follow_up_tasks"
                    " (id, tenant_id, workspace_id, contact_id, type, status,"
                    "  source_inbox_message_id, result_outbound_message_id,"
                    "  attempts, notes)"
                    " VALUES (:id, :tid, :wid, :cid, 'question_followup',"
                    "  'awaiting_approval', :inbox, :draft, 1, 'Question from reply.')"
                ),
                {
                    "id": task_id,
                    "tid": tenant_id,
                    "wid": workspace_id,
                    "cid": contact_id,
                    "inbox": str(uuid.uuid4()),
                    "draft": draft_id,
                },
            )
    finally:
        await seed.dispose()
    return task_id, draft_id


# ── GET /review ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_returns_task_and_draft(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)
    task_id, draft_id = await _seed_parked_followup(
        db_engine, claims["org_id"], claims["workspace_id"]
    )

    resp = await api_client.get(
        f"/api/v1/crm/follow-ups/{task_id}/review", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task"]["id"] == task_id
    assert body["task"]["result_outbound_message_id"] == draft_id
    assert body["draft"]["id"] == draft_id
    assert body["draft"]["status"] == "draft"
    assert body["reply"] is None  # no inbox row seeded


@pytest.mark.asyncio
async def test_review_unauthenticated_returns_401(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"/api/v1/crm/follow-ups/{uuid.uuid4()}/review")
    assert resp.status_code == 401


# ── PATCH /draft ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_draft_updates_body(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)
    task_id, _ = await _seed_parked_followup(
        db_engine, claims["org_id"], claims["workspace_id"]
    )

    resp = await api_client.patch(
        f"/api/v1/crm/follow-ups/{task_id}/draft",
        json={"subject": "Re: Edited", "body": "An edited, more precise answer."},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["body"] == "An edited, more precise answer."

    review = await api_client.get(
        f"/api/v1/crm/follow-ups/{task_id}/review", headers=_auth(token)
    )
    assert review.json()["draft"]["body"] == "An edited, more precise answer."


# ── POST /reject ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_cancels_task(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)
    task_id, _ = await _seed_parked_followup(
        db_engine, claims["org_id"], claims["workspace_id"]
    )

    resp = await api_client.post(
        f"/api/v1/crm/follow-ups/{task_id}/reject",
        json={"reason": "Not relevant to this contact."},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"

    # Once cancelled, the task is no longer reviewable → 409.
    review = await api_client.get(
        f"/api/v1/crm/follow-ups/{task_id}/review", headers=_auth(token)
    )
    assert review.status_code == 409


# ── POST /approve ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_sends_and_marks_done(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)
    task_id, draft_id = await _seed_parked_followup(
        db_engine, claims["org_id"], claims["workspace_id"]
    )

    queued = SendMessageResponse(message_id=uuid.UUID(draft_id), status="queued")
    with patch(
        "corpmind.modules.outreach.service.OutreachService.send_message",
        new_callable=AsyncMock,
        return_value=queued,
    ) as mock_send:
        resp = await api_client.post(
            f"/api/v1/crm/follow-ups/{task_id}/approve", headers=_auth(token)
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"
    mock_send.assert_awaited_once()

    # Task left awaiting_approval → review now 409.
    review = await api_client.get(
        f"/api/v1/crm/follow-ups/{task_id}/review", headers=_auth(token)
    )
    assert review.status_code == 409


@pytest.mark.asyncio
async def test_approve_compliance_block_cancels(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    claims = _claims(token)
    task_id, draft_id = await _seed_parked_followup(
        db_engine, claims["org_id"], claims["workspace_id"]
    )

    blocked = SendMessageResponse(
        message_id=uuid.UUID(draft_id), status="blocked", compliance_reason="frequency_cap"
    )
    with patch(
        "corpmind.modules.outreach.service.OutreachService.send_message",
        new_callable=AsyncMock,
        return_value=blocked,
    ):
        resp = await api_client.post(
            f"/api/v1/crm/follow-ups/{task_id}/approve", headers=_auth(token)
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["compliance_reason"] == "frequency_cap"


@pytest.mark.asyncio
async def test_approve_unknown_task_returns_404(api_client: AsyncClient) -> None:
    user = await make_user(api_client)
    token = user["tokens"]["access_token"]
    resp = await api_client.post(
        f"/api/v1/crm/follow-ups/{uuid.uuid4()}/approve", headers=_auth(token)
    )
    assert resp.status_code == 404


# ── Tenant isolation ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_b_cannot_review_tenant_a_task(
    api_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    a = await make_user(api_client)
    a_claims = _claims(a["tokens"]["access_token"])
    task_id, _ = await _seed_parked_followup(
        db_engine, a_claims["org_id"], a_claims["workspace_id"]
    )

    b = await make_user(api_client)
    b_token = b["tokens"]["access_token"]

    resp = await api_client.get(
        f"/api/v1/crm/follow-ups/{task_id}/review", headers=_auth(b_token)
    )
    assert resp.status_code == 404, "Tenant B must not see Tenant A's follow-up"
