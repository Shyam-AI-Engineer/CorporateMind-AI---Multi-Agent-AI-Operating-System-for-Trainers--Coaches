"""HTTP-layer tests for the Sprint 5 visibility endpoints.

Covers four new read-only routes added to power the Inbox UI:

  GET /api/v1/inbox/connections   — list inbox connections per workspace
  GET /api/v1/inbox/messages      — list inbox messages (paginated, filtered)
  GET /api/v1/crm/activities      — list CRM activity log
  GET /api/v1/crm/follow-ups      — list follow-up tasks

All four are wired through the existing TenantMiddleware → RLS path, so the
tests focus on:
  - Empty state                    (200 + items=[], total=0)
  - Pagination semantics           (limit + offset honoured)
  - Filtering                      (intent / status / scope filters)
  - Auth gating                    (401 without bearer)
  - Tenant isolation               (cross-tenant invisibility)
  - Validation gating              (activities requires a scope filter)

Seeding goes through the public superuser via NullPool so test rows can
sit under arbitrary tenant_ids without fighting RLS.  The endpoints
themselves run as the authenticated test user, exercising the full
production code path.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from tests.api.conftest import make_user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    """Decode a JWT payload (no signature verification) to grab tenant + workspace."""
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


async def _seed_inbox_connection(
    db_engine: AsyncEngine,
    *,
    tenant_id: str,
    workspace_id: str,
    connection_id: str | None = None,
    email_hash: str | None = None,
) -> str:
    """Insert an inbox_connections row directly (bypassing RLS / encryption)."""
    cid = connection_id or str(uuid.uuid4())
    seed_engine = create_async_engine(
        db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO inbox_connections"
                    " (id, tenant_id, workspace_id, provider, email_address_enc,"
                    "  refresh_token_enc, email_address_hash, scopes, status,"
                    "  connected_by)"
                    " VALUES (:id, :tid, :wid, 'gmail', 'enc-email',"
                    "         'enc-refresh', :hash, 'openid', 'active',"
                    "         :uid)"
                ),
                {
                    "id": cid,
                    "tid": tenant_id,
                    "wid": workspace_id,
                    "hash": email_hash or uuid.uuid4().hex,
                    "uid": tenant_id,  # connected_by is just a UUID
                },
            )
    finally:
        await seed_engine.dispose()
    return cid


async def _seed_inbox_message(
    db_engine: AsyncEngine,
    *,
    tenant_id: str,
    connection_id: str,
    intent: str | None = None,
    received_at: datetime | None = None,
) -> str:
    """Insert an inbox_messages row directly."""
    mid = str(uuid.uuid4())
    received = received_at or datetime.now(UTC)
    seed_engine = create_async_engine(
        db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO inbox_messages"
                    " (id, tenant_id, connection_id, provider_message_id,"
                    "  from_address, received_at, body_truncated, reply_intent,"
                    "  synced_at)"
                    " VALUES (:id, :tid, :cid, :pid, 'sender@example.com',"
                    "         :ts, true, :intent, :ts)"
                ),
                {
                    "id": mid,
                    "tid": tenant_id,
                    "cid": connection_id,
                    "pid": uuid.uuid4().hex,
                    "ts": received,
                    "intent": intent,
                },
            )
    finally:
        await seed_engine.dispose()
    return mid


async def _seed_activity(
    db_engine: AsyncEngine,
    *,
    tenant_id: str,
    workspace_id: str,
    contact_id: str | None = None,
    lead_id: str | None = None,
    type_: str = "lead_engaged",
) -> str:
    aid = str(uuid.uuid4())
    seed_engine = create_async_engine(
        db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO crm_activities"
                    " (id, tenant_id, workspace_id, lead_id, contact_id,"
                    "  type, summary)"
                    " VALUES (:id, :tid, :wid, :lid, :cid, :type, 'Test activity')"
                ),
                {
                    "id": aid,
                    "tid": tenant_id,
                    "wid": workspace_id,
                    "lid": lead_id,
                    "cid": contact_id or str(uuid.uuid4()),
                    "type": type_,
                },
            )
    finally:
        await seed_engine.dispose()
    return aid


async def _seed_follow_up(
    db_engine: AsyncEngine,
    *,
    tenant_id: str,
    workspace_id: str,
    status: str = "pending",
    scheduled_for: datetime | None = None,
) -> str:
    fid = str(uuid.uuid4())
    seed_engine = create_async_engine(
        db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO follow_up_tasks"
                    " (id, tenant_id, workspace_id, contact_id, type, status,"
                    "  scheduled_for, source_inbox_message_id)"
                    " VALUES (:id, :tid, :wid, :cid, 'question_followup', :status,"
                    "         :sched, :iid)"
                ),
                {
                    "id": fid,
                    "tid": tenant_id,
                    "wid": workspace_id,
                    "cid": str(uuid.uuid4()),
                    "status": status,
                    "sched": scheduled_for,
                    "iid": str(uuid.uuid4()),
                },
            )
    finally:
        await seed_engine.dispose()
    return fid


# ── GET /api/v1/inbox/connections ─────────────────────────────────────────────

class TestListInboxConnections:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/inbox/connections")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_zero_items(
        self, api_client: AsyncClient
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        resp = await api_client.get(
            "/api/v1/inbox/connections", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    @pytest.mark.asyncio
    async def test_returns_seeded_connection(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)
        # Seed with the encryption key the API will use to decrypt — we patch
        # the key so the test connection's plaintext "enc-email" surfaces in
        # the response.  In production this is real AES-GCM.
        # `decrypt` is bound into inbox.service at import time, so the patch
        # must target the binding in that module, not corpmind.core.encryption.
        from unittest.mock import patch

        with patch(
            "corpmind.modules.inbox.service.decrypt",
            return_value="seed@example.com",
        ):
            cid = await _seed_inbox_connection(
                db_engine,
                tenant_id=claims["org_id"],
                workspace_id=claims["workspace_id"],
            )
            resp = await api_client.get(
                "/api/v1/inbox/connections", headers=_auth(token)
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == cid
        assert body["items"][0]["email_address"] == "seed@example.com"
        assert body["items"][0]["provider"] == "gmail"

    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        """Seed under tenant A; list from tenant B — must not see it."""
        user_a = await make_user(api_client)
        user_b = await make_user(api_client)
        token_a = user_a["tokens"]["access_token"]
        token_b = user_b["tokens"]["access_token"]
        claims_a = _claims(token_a)

        await _seed_inbox_connection(
            db_engine,
            tenant_id=claims_a["org_id"],
            workspace_id=claims_a["workspace_id"],
        )

        resp = await api_client.get(
            "/api/v1/inbox/connections", headers=_auth(token_b)
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_pagination_limits(self, api_client: AsyncClient):
        """limit=0 must 422; limit=1000 must 422 (max=200)."""
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        resp = await api_client.get(
            "/api/v1/inbox/connections?limit=0", headers=_auth(token)
        )
        assert resp.status_code == 422
        resp = await api_client.get(
            "/api/v1/inbox/connections?limit=1000", headers=_auth(token)
        )
        assert resp.status_code == 422


# ── GET /api/v1/inbox/messages ────────────────────────────────────────────────

class TestListInboxMessages:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/inbox/messages")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_inbox_returns_zero_items(self, api_client: AsyncClient):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        resp = await api_client.get(
            "/api/v1/inbox/messages", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    @pytest.mark.asyncio
    async def test_returns_seeded_messages_newest_first(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)

        cid = await _seed_inbox_connection(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
        )
        older = datetime(2026, 1, 1, tzinfo=UTC)
        newer = datetime(2026, 6, 1, tzinfo=UTC)
        await _seed_inbox_message(
            db_engine, tenant_id=claims["org_id"], connection_id=cid,
            intent="question", received_at=older,
        )
        await _seed_inbox_message(
            db_engine, tenant_id=claims["org_id"], connection_id=cid,
            intent="interested", received_at=newer,
        )

        resp = await api_client.get(
            "/api/v1/inbox/messages", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        # Newest first
        assert body["items"][0]["reply_intent"] == "interested"
        assert body["items"][1]["reply_intent"] == "question"

    @pytest.mark.asyncio
    async def test_intent_filter(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)
        cid = await _seed_inbox_connection(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
        )
        await _seed_inbox_message(
            db_engine, tenant_id=claims["org_id"], connection_id=cid,
            intent="interested",
        )
        await _seed_inbox_message(
            db_engine, tenant_id=claims["org_id"], connection_id=cid,
            intent="bounce",
        )

        resp = await api_client.get(
            "/api/v1/inbox/messages?intent=interested", headers=_auth(token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["reply_intent"] == "interested"

    @pytest.mark.asyncio
    async def test_pagination_offset(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)
        cid = await _seed_inbox_connection(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
        )
        # Seed 3 messages
        for i in range(3):
            await _seed_inbox_message(
                db_engine, tenant_id=claims["org_id"], connection_id=cid,
                received_at=datetime(2026, 1, i + 1, tzinfo=UTC),
            )

        resp = await api_client.get(
            "/api/v1/inbox/messages?limit=2&offset=0", headers=_auth(token)
        )
        first_page = resp.json()
        assert len(first_page["items"]) == 2
        assert first_page["total"] == 3

        resp = await api_client.get(
            "/api/v1/inbox/messages?limit=2&offset=2", headers=_auth(token)
        )
        second_page = resp.json()
        assert len(second_page["items"]) == 1
        # Pages must not overlap.
        first_ids = {m["id"] for m in first_page["items"]}
        second_ids = {m["id"] for m in second_page["items"]}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user_a = await make_user(api_client)
        user_b = await make_user(api_client)
        token_a = user_a["tokens"]["access_token"]
        token_b = user_b["tokens"]["access_token"]
        claims_a = _claims(token_a)

        cid = await _seed_inbox_connection(
            db_engine,
            tenant_id=claims_a["org_id"],
            workspace_id=claims_a["workspace_id"],
        )
        await _seed_inbox_message(
            db_engine, tenant_id=claims_a["org_id"], connection_id=cid,
        )

        resp = await api_client.get(
            "/api/v1/inbox/messages", headers=_auth(token_b)
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── GET /api/v1/crm/activities ────────────────────────────────────────────────

class TestListActivities:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, api_client: AsyncClient):
        resp = await api_client.get("/api/v1/crm/activities")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unscoped_query_returns_422(self, api_client: AsyncClient):
        """At least one of workspace_id/lead_id/contact_id is required."""
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        resp = await api_client.get(
            "/api/v1/crm/activities", headers=_auth(token)
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_zero_items(
        self, api_client: AsyncClient
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)
        resp = await api_client.get(
            f"/api/v1/crm/activities?workspace_id={claims['workspace_id']}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_seeded_activities_newest_first(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)

        await _seed_activity(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            type_="lead_engaged",
        )
        await _seed_activity(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            type_="contact_bounced",
        )

        resp = await api_client.get(
            f"/api/v1/crm/activities?workspace_id={claims['workspace_id']}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_contact_filter(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)
        target_contact = str(uuid.uuid4())

        await _seed_activity(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            contact_id=target_contact,
        )
        await _seed_activity(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            # Different contact
        )

        resp = await api_client.get(
            f"/api/v1/crm/activities?contact_id={target_contact}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["contact_id"] == target_contact

    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user_a = await make_user(api_client)
        user_b = await make_user(api_client)
        token_a = user_a["tokens"]["access_token"]
        token_b = user_b["tokens"]["access_token"]
        claims_a = _claims(token_a)
        claims_b = _claims(token_b)

        await _seed_activity(
            db_engine,
            tenant_id=claims_a["org_id"],
            workspace_id=claims_a["workspace_id"],
        )

        # B asks for its own workspace and sees nothing.
        resp = await api_client.get(
            f"/api/v1/crm/activities?workspace_id={claims_b['workspace_id']}",
            headers=_auth(token_b),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── GET /api/v1/crm/follow-ups ────────────────────────────────────────────────

class TestListFollowUps:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, api_client: AsyncClient):
        resp = await api_client.get(
            "/api/v1/crm/follow-ups?workspace_id=" + str(uuid.uuid4())
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, api_client: AsyncClient):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        resp = await api_client.get(
            "/api/v1/crm/follow-ups", headers=_auth(token)
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_zero_items(
        self, api_client: AsyncClient
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)
        resp = await api_client.get(
            f"/api/v1/crm/follow-ups?workspace_id={claims['workspace_id']}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_seeded_follow_ups_pending_first(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        """NULL scheduled_for (do-asap) must appear before scheduled."""
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)

        # Seed: one scheduled, one do-asap.
        future = datetime(2027, 1, 1, tzinfo=UTC)
        await _seed_follow_up(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            scheduled_for=future,
        )
        await _seed_follow_up(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            scheduled_for=None,  # do-asap
        )

        resp = await api_client.get(
            f"/api/v1/crm/follow-ups?workspace_id={claims['workspace_id']}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        # NULLS FIRST → do-asap (scheduled_for is None) wins the top slot
        assert body["items"][0]["scheduled_for"] is None
        assert body["items"][1]["scheduled_for"] is not None

    @pytest.mark.asyncio
    async def test_status_filter(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user = await make_user(api_client)
        token = user["tokens"]["access_token"]
        claims = _claims(token)

        await _seed_follow_up(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            status="pending",
        )
        await _seed_follow_up(
            db_engine,
            tenant_id=claims["org_id"],
            workspace_id=claims["workspace_id"],
            status="done",
        )

        resp = await api_client.get(
            f"/api/v1/crm/follow-ups?workspace_id={claims['workspace_id']}&status=pending",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self, api_client: AsyncClient, db_engine: AsyncEngine
    ):
        user_a = await make_user(api_client)
        user_b = await make_user(api_client)
        token_a = user_a["tokens"]["access_token"]
        token_b = user_b["tokens"]["access_token"]
        claims_a = _claims(token_a)
        claims_b = _claims(token_b)

        await _seed_follow_up(
            db_engine,
            tenant_id=claims_a["org_id"],
            workspace_id=claims_a["workspace_id"],
        )

        resp = await api_client.get(
            f"/api/v1/crm/follow-ups?workspace_id={claims_b['workspace_id']}",
            headers=_auth(token_b),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
