"""Integration tests for ProposalRepo.

Uses the session-scoped PostgreSQL testcontainer from root conftest.
Tests are isolated by UUID uniqueness — no per-test rollback needed.

Both layers of tenant protection are exercised:
  1. App-layer  — repo queries filter via TenantContext.org_id from ContextVar.
  2. DB-layer   — PostgreSQL RLS enforced because db_session runs as the
                  non-superuser corpmind_test role (see conftest._setup_test_role).

All writes use session.flush() within the shared transaction; data is visible
to subsequent reads in the same test without touching the persistent store.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from corpmind.core.database import set_rls_tenant
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.proposals.models import Proposal
from corpmind.modules.proposals.repo import ProposalRepo


# ── Object factory ─────────────────────────────────────────────────────────────

def _proposal(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    status: str = "draft",
    created_at: datetime | None = None,
) -> Proposal:
    p = Proposal(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        contact_id=uuid.uuid4(),
        title=f"Test Proposal {uuid.uuid4().hex[:6]}",
        status=status,
        content={
            "title": "Leadership Excellence Workshop",
            "executive_summary": "A brief summary.",
            "value_proposition": ["Outcome 1", "Outcome 2", "Outcome 3"],
            "proposed_training": {
                "topic": "Leadership",
                "duration": "2-day",
                "format": "in-person",
                "participants": "20-30",
            },
            "proposed_agenda": [],
            "investment": "TBD",
            "call_to_action": "Schedule a call",
        },
    )
    if created_at is not None:
        p.created_at = created_at
    return p


# ── ProposalRepo.create ────────────────────────────────────────────────────────

class TestProposalRepoCreate:
    @pytest.mark.asyncio
    async def test_create_persists_and_returns_proposal(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            repo = ProposalRepo(db_session)
            created = await repo.create(prop)
            await db_session.flush()

            assert created.id is not None
            assert created.tenant_id == tenant_a.org_id
            assert created.workspace_id == tenant_a.workspace_id
            assert created.status == "draft"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_create_stores_content_jsonb(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            repo = ProposalRepo(db_session)
            created = await repo.create(prop)
            await db_session.flush()

            assert isinstance(created.content, dict)
            assert created.content["title"] == "Leadership Excellence Workshop"
            assert created.content["call_to_action"] == "Schedule a call"
        finally:
            clear_tenant_context(token)


# ── ProposalRepo.find_by_id ────────────────────────────────────────────────────

class TestProposalRepoFindById:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_own_proposal(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            repo = ProposalRepo(db_session)
            created = await repo.create(prop)
            await db_session.flush()

            found = await repo.find_by_id(created.id)
            assert found is not None
            assert found.id == created.id
            assert found.tenant_id == tenant_a.org_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_for_unknown_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            result = await repo.find_by_id(uuid.uuid4())
            assert result is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_by_id_invisible_to_other_tenant(
        self, db_session, tenant_a, tenant_b
    ):
        # Write as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        repo = ProposalRepo(db_session)
        created = await repo.create(prop)
        await db_session.flush()
        proposal_id = created.id
        clear_tenant_context(token_a)

        # Read as tenant B — must return None
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            result = await repo.find_by_id(proposal_id)
            assert result is None, "Tenant B must not see Tenant A's proposal"
        finally:
            clear_tenant_context(token_b)


# ── ProposalRepo.list_by_workspace ─────────────────────────────────────────────

class TestProposalRepoListByWorkspace:
    @pytest.mark.asyncio
    async def test_list_returns_proposals_for_workspace(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            p1 = await repo.create(_proposal(tenant_a.org_id, tenant_a.workspace_id))
            p2 = await repo.create(_proposal(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()

            results = await repo.list_by_workspace(tenant_a.workspace_id)
            ids = [r.id for r in results]
            assert p1.id in ids
            assert p2.id in ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_list_ordered_by_created_desc(self, db_session, tenant_a):
        """Most recently created proposal appears first in DESC order.

        Explicit created_at values are set on the Python objects because
        PostgreSQL's server_default=func.now() resolves to transaction start
        time — both rows would otherwise get the same timestamp, making the
        ordering assertion non-deterministic.
        """
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            now = datetime.now(UTC)
            repo = ProposalRepo(db_session)
            older = _proposal(
                tenant_a.org_id, tenant_a.workspace_id,
                created_at=now - timedelta(seconds=10),
            )
            newer = _proposal(
                tenant_a.org_id, tenant_a.workspace_id,
                created_at=now,
            )
            await repo.create(older)
            await repo.create(newer)
            await db_session.flush()

            results = await repo.list_by_workspace(tenant_a.workspace_id)
            ids = [r.id for r in results]
            # newer has a later created_at, so it must appear before older in DESC order
            assert ids.index(newer.id) < ids.index(older.id)
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_list_returns_empty_for_unknown_workspace(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            results = await repo.list_by_workspace(uuid.uuid4())
            assert results == []
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_list_does_not_expose_other_tenant_proposals(
        self, db_session, tenant_a, tenant_b
    ):
        # Write two proposals as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        repo = ProposalRepo(db_session)
        p = await repo.create(_proposal(tenant_a.org_id, tenant_a.workspace_id))
        await db_session.flush()
        a_workspace = tenant_a.workspace_id
        clear_tenant_context(token_a)

        # List using tenant A's workspace_id but under tenant B's context
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            results = await repo.list_by_workspace(a_workspace)
            ids = [r.id for r in results]
            assert p.id not in ids, "Tenant B must not see Tenant A's proposals"
        finally:
            clear_tenant_context(token_b)

    @pytest.mark.asyncio
    async def test_list_pagination_limit(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            for _ in range(4):
                await repo.create(_proposal(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()

            results = await repo.list_by_workspace(
                tenant_a.workspace_id, limit=2, offset=0
            )
            assert len(results) <= 2
        finally:
            clear_tenant_context(token)


# ── ProposalRepo.count_by_workspace ───────────────────────────────────────────

class TestProposalRepoCountByWorkspace:
    @pytest.mark.asyncio
    async def test_count_returns_correct_number(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            ws_id = uuid.uuid4()  # isolated workspace to avoid interference
            # Override workspace_id for isolation
            for _ in range(3):
                p = _proposal(tenant_a.org_id, tenant_a.workspace_id)
                p.workspace_id = ws_id
                await repo.create(p)
            await db_session.flush()

            count = await repo.count_by_workspace(ws_id)
            assert count == 3
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_count_returns_zero_for_unknown_workspace(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            count = await repo.count_by_workspace(uuid.uuid4())
            assert count == 0
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_count_zero_for_other_tenants_workspace(
        self, db_session, tenant_a, tenant_b
    ):
        """Tenant B calling count with tenant A's workspace_id returns 0."""
        # Create proposals as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        repo = ProposalRepo(db_session)
        ws_id = uuid.uuid4()
        for _ in range(2):
            p = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            p.workspace_id = ws_id
            await repo.create(p)
        await db_session.flush()
        clear_tenant_context(token_a)

        # Count as tenant B
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            count = await repo.count_by_workspace(ws_id)
            assert count == 0, "Tenant B must not count Tenant A's proposals"
        finally:
            clear_tenant_context(token_b)


# ── ProposalRepo.update_fields ─────────────────────────────────────────────────

class TestProposalRepoUpdateFields:
    @pytest.mark.asyncio
    async def test_update_status_to_sent(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            created = await repo.create(prop)
            await db_session.flush()

            # Save PK before expire — accessing attributes on an expired object
            # triggers a synchronous lazy-load in async SQLAlchemy (MissingGreenlet).
            proposal_id = created.id

            # Must approve before sending — CHECK constraint enforces this at DB level.
            await repo.update_fields(proposal_id, approval_status="approved")
            sent_at = datetime.now(UTC)
            await repo.update_fields(proposal_id, status="sent", sent_at=sent_at)
            await db_session.flush()

            db_session.expire(created)
            found = await repo.find_by_id(proposal_id)
            assert found is not None
            assert found.status == "sent"
            assert found.sent_at is not None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_update_wrong_tenant_is_noop(
        self, db_session, tenant_a, tenant_b
    ):
        """update_fields under tenant B's context does not touch tenant A's rows."""
        # Create as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        repo = ProposalRepo(db_session)
        prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        created = await repo.create(prop)
        await db_session.flush()
        proposal_id = created.id
        clear_tenant_context(token_a)

        # Update attempt as tenant B
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        await repo.update_fields(proposal_id, status="sent", sent_at=datetime.now(UTC))
        await db_session.flush()
        clear_tenant_context(token_b)

        # Verify original status unchanged when reading as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            db_session.expire(created)
            found = await repo.find_by_id(proposal_id)
            assert found is not None
            assert found.status == "draft", "Tenant B's update must not affect Tenant A's proposal"
        finally:
            clear_tenant_context(token_a)


# ── ProposalRepo.find_by_id_for_update ────────────────────────────────────────

class TestProposalRepoFindByIdForUpdate:
    @pytest.mark.asyncio
    async def test_find_for_update_returns_proposal(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            repo = ProposalRepo(db_session)
            created = await repo.create(prop)
            await db_session.flush()

            found = await repo.find_by_id_for_update(created.id)
            assert found is not None
            assert found.id == created.id
            assert found.approval_status == "pending_approval"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_for_update_returns_none_for_unknown_id(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = ProposalRepo(db_session)
            result = await repo.find_by_id_for_update(uuid.uuid4())
            assert result is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_find_for_update_invisible_to_other_tenant(
        self, db_session, tenant_a, tenant_b
    ):
        # Write as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        repo = ProposalRepo(db_session)
        created = await repo.create(prop)
        await db_session.flush()
        proposal_id = created.id
        clear_tenant_context(token_a)

        # FOR UPDATE as tenant B — must return None (RLS filters the row)
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            result = await repo.find_by_id_for_update(proposal_id)
            assert result is None, "Tenant B must not lock Tenant A's proposal row"
        finally:
            clear_tenant_context(token_b)


# ── ProposalRepo.list_by_workspace (approval_status filter) ───────────────────

class TestProposalRepoListApprovalFilter:
    @pytest.mark.asyncio
    async def test_list_filters_by_approval_status_pending(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            ws_id = uuid.uuid4()
            repo = ProposalRepo(db_session)

            pending = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            pending.workspace_id = ws_id
            created_pending = await repo.create(pending)

            approved = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            approved.workspace_id = ws_id
            created_approved = await repo.create(approved)
            await db_session.flush()

            # Directly update approval_status via update_fields
            await repo.update_fields(created_approved.id, approval_status="approved")
            await db_session.flush()

            results = await repo.list_by_workspace(ws_id, approval_status="pending_approval")
            ids = [r.id for r in results]
            assert created_pending.id in ids
            assert created_approved.id not in ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_count_filters_by_approval_status(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            ws_id = uuid.uuid4()
            repo = ProposalRepo(db_session)

            for _ in range(2):
                p = _proposal(tenant_a.org_id, tenant_a.workspace_id)
                p.workspace_id = ws_id
                await repo.create(p)

            approved = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            approved.workspace_id = ws_id
            created_approved = await repo.create(approved)
            await db_session.flush()
            await repo.update_fields(created_approved.id, approval_status="approved")
            await db_session.flush()

            pending_count = await repo.count_by_workspace(ws_id, approval_status="pending_approval")
            approved_count = await repo.count_by_workspace(ws_id, approval_status="approved")
            assert pending_count == 2
            assert approved_count == 1
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_approval_filter_cross_tenant_invisible(
        self, db_session, tenant_a, tenant_b
    ):
        """Tenant B cannot see Tenant A's pending proposals via the approval filter."""
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        repo = ProposalRepo(db_session)
        p = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        await repo.create(p)
        await db_session.flush()
        a_workspace = tenant_a.workspace_id
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            results = await repo.list_by_workspace(
                a_workspace, approval_status="pending_approval"
            )
            assert results == [], "Tenant B must not see Tenant A's pending proposals"
        finally:
            clear_tenant_context(token_b)


# ── ProposalRepo — outbound_message_id (Sprint 12B) ───────────────────────────

class TestProposalRepoOutboundMessageId:
    @pytest.mark.asyncio
    async def test_outbound_message_id_null_by_default(self, db_session, tenant_a):
        """Newly created proposals have outbound_message_id = NULL."""
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            repo = ProposalRepo(db_session)
            created = await repo.create(prop)
            await db_session.flush()

            found = await repo.find_by_id(created.id)
            assert found is not None
            assert found.outbound_message_id is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_outbound_message_id_roundtrip(self, db_session, tenant_a):
        """update_fields can set outbound_message_id; find_by_id reads it back."""
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
            repo = ProposalRepo(db_session)
            created = await repo.create(prop)
            await db_session.flush()
            proposal_id = created.id

            # approval_status must be 'approved' before setting status='sent'
            # (CHECK constraint). Set both at once.
            fake_outbound_id = uuid.uuid4()
            await repo.update_fields(
                proposal_id,
                approval_status="approved",
                outbound_message_id=fake_outbound_id,
                status="sent",
                sent_at=datetime.now(UTC),
            )
            await db_session.flush()

            db_session.expire(created)
            found = await repo.find_by_id(proposal_id)
            assert found is not None
            assert found.outbound_message_id == fake_outbound_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_tenant_isolation_outbound_message_id(
        self, db_session, tenant_a, tenant_b
    ):
        """Tenant B cannot read the outbound_message_id set on Tenant A's proposal."""
        # Write as tenant A
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        repo = ProposalRepo(db_session)
        created = await repo.create(prop)
        await db_session.flush()
        proposal_id = created.id
        fake_outbound_id = uuid.uuid4()
        await repo.update_fields(
            proposal_id,
            approval_status="approved",
            outbound_message_id=fake_outbound_id,
            status="sent",
            sent_at=datetime.now(UTC),
        )
        await db_session.flush()
        clear_tenant_context(token_a)

        # Read as tenant B — proposal must be invisible
        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            found = await repo.find_by_id(proposal_id)
            assert found is None, "Tenant B must not see Tenant A's delivery link"
        finally:
            clear_tenant_context(token_b)


# ── RLS DB-layer isolation ─────────────────────────────────────────────────────

class TestProposalRepoRLS:
    @pytest.mark.asyncio
    async def test_rls_blocks_direct_sql_cross_tenant_read(
        self, db_session, tenant_a, tenant_b
    ):
        """Raw SQL SELECT under tenant B's RLS context cannot read tenant A's row."""
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        repo = ProposalRepo(db_session)
        created = await repo.create(prop)
        await db_session.flush()
        proposal_id = created.id
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            rows = await db_session.execute(
                text("SELECT id FROM proposals WHERE id = :pid"),
                {"pid": str(proposal_id)},
            )
            assert rows.first() is None, (
                "RLS must block Tenant B from reading Tenant A's proposal via raw SQL"
            )
        finally:
            clear_tenant_context(token_b)

    @pytest.mark.asyncio
    async def test_rls_fail_closed_without_tenant_context(self, db_session, tenant_a):
        """When app.tenant_id is not set, RLS returns zero rows (fail-closed)."""
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        prop = _proposal(tenant_a.org_id, tenant_a.workspace_id)
        repo = ProposalRepo(db_session)
        created = await repo.create(prop)
        await db_session.flush()
        proposal_id = created.id
        clear_tenant_context(token_a)

        await db_session.execute(text("RESET app.tenant_id"))
        rows = await db_session.execute(
            text("SELECT id FROM proposals WHERE id = :pid"),
            {"pid": str(proposal_id)},
        )
        assert rows.first() is None, (
            "Without app.tenant_id, RLS must return zero rows (fail-closed)"
        )
