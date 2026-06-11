"""Integration tests for the Sprint 8B FollowUpTaskRepo cadence methods.

Uses the session-scoped PostgreSQL testcontainer (root conftest).  Exercises
both tenant-protection layers (app-filter via TenantContext + DB RLS via the
non-superuser corpmind_test role), same convention as test_proposal_repo.py.

Focus: the correctness-critical DB logic the cadence depends on —
  • list_due window + ordering
  • atomic claim (single winner, attempts increment, tenant isolation)
  • terminal transitions (done / awaiting_approval / cancelled)
  • defer (processing → pending with new schedule)
  • reset_stuck_processing reaper
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from corpmind.core.database import set_rls_tenant
from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.crm.models import FollowUpTask
from corpmind.modules.crm.repo import FollowUpTaskRepo


def _task(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    status: str = "pending",
    scheduled_for: datetime | None = None,
    type: str = "question_followup",
    attempts: int = 0,
    updated_at: datetime | None = None,
) -> FollowUpTask:
    t = FollowUpTask(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        contact_id=uuid.uuid4(),
        type=type,
        status=status,
        scheduled_for=scheduled_for,
        source_inbox_message_id=uuid.uuid4(),  # unique → satisfies UNIQUE(tenant, src)
        source_outbound_message_id=uuid.uuid4(),
        notes="seed",
        attempts=attempts,
    )
    if updated_at is not None:
        t.updated_at = updated_at
    return t


# ── list_due ─────────────────────────────────────────────────────────────────

class TestListDue:
    @pytest.mark.asyncio
    async def test_includes_null_and_past_excludes_future(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            now = datetime.now(UTC)
            asap = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id, scheduled_for=None))
            past = await repo.create(
                _task(tenant_a.org_id, tenant_a.workspace_id, scheduled_for=now - timedelta(hours=1))
            )
            future = await repo.create(
                _task(tenant_a.org_id, tenant_a.workspace_id, scheduled_for=now + timedelta(hours=2))
            )
            await db_session.flush()

            due_ids = [t.id for t in await repo.list_due(limit=50)]
            assert asap.id in due_ids
            assert past.id in due_ids
            assert future.id not in due_ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_excludes_non_pending(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            done = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id, status="done"))
            proc = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id, status="processing"))
            await db_session.flush()

            due_ids = [t.id for t in await repo.list_due(limit=50)]
            assert done.id not in due_ids
            assert proc.id not in due_ids
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_null_scheduled_sorts_before_timed(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            ws = uuid.uuid4()  # isolate
            now = datetime.now(UTC)
            timed = await repo.create(
                _task(tenant_a.org_id, ws, scheduled_for=now - timedelta(minutes=5))
            )
            asap = await repo.create(_task(tenant_a.org_id, ws, scheduled_for=None))
            await db_session.flush()

            ordered = [t.id for t in await repo.list_due(limit=50) if t.workspace_id == ws]
            assert ordered.index(asap.id) < ordered.index(timed.id)
        finally:
            clear_tenant_context(token)


# ── claim ────────────────────────────────────────────────────────────────────

class TestClaim:
    @pytest.mark.asyncio
    async def test_first_claim_wins_and_increments_attempts(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()
            tid = t.id
            src = t.source_inbox_message_id  # capture before expire (async lazy-load is unsafe)

            assert await repo.claim(tid) is True
            await db_session.flush()

            db_session.expire(t)
            reloaded = await repo.find_by_inbox_message(src)
            assert reloaded.status == "processing"
            assert reloaded.attempts == 1
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_second_claim_on_processing_row_returns_false(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()

            assert await repo.claim(t.id) is True
            await db_session.flush()
            # Row is now 'processing' — the guarded UPDATE matches zero rows.
            assert await repo.claim(t.id) is False
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_claim_invisible_across_tenant(self, db_session, tenant_a, tenant_b):
        token_a = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        repo = FollowUpTaskRepo(db_session)
        t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id))
        await db_session.flush()
        tid = t.id
        clear_tenant_context(token_a)

        token_b = set_tenant_context(tenant_b)
        await set_rls_tenant(db_session, tenant_b.org_id)
        try:
            assert await repo.claim(tid) is False, "Tenant B must not claim Tenant A's task"
        finally:
            clear_tenant_context(token_b)


# ── terminal transitions ───────────────────────────────────────────────────────

class TestTransitions:
    @pytest.mark.asyncio
    async def test_mark_done_sets_status_and_result(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()
            src = t.source_inbox_message_id
            result_id = uuid.uuid4()

            await repo.mark_done(t.id, result_outbound_message_id=result_id)
            await db_session.flush()
            db_session.expire(t)
            reloaded = await repo.find_by_inbox_message(src)
            assert reloaded.status == "done"
            assert reloaded.result_outbound_message_id == result_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_mark_awaiting_approval(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()
            src = t.source_inbox_message_id
            result_id = uuid.uuid4()

            await repo.mark_awaiting_approval(t.id, result_outbound_message_id=result_id)
            await db_session.flush()
            db_session.expire(t)
            reloaded = await repo.find_by_inbox_message(src)
            assert reloaded.status == "awaiting_approval"
            assert reloaded.result_outbound_message_id == result_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_mark_cancelled_appends_reason(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id))
            await db_session.flush()
            src = t.source_inbox_message_id

            await repo.mark_cancelled(t.id, reason="opt_in")
            await db_session.flush()
            db_session.expire(t)
            reloaded = await repo.find_by_inbox_message(src)
            assert reloaded.status == "cancelled"
            assert "seed" in reloaded.notes  # original preserved
            assert "opt_in" in reloaded.notes  # reason appended
        finally:
            clear_tenant_context(token)


# ── defer ──────────────────────────────────────────────────────────────────────

class TestDefer:
    @pytest.mark.asyncio
    async def test_defer_returns_processing_row_to_pending_with_schedule(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id, status="processing"))
            await db_session.flush()
            src = t.source_inbox_message_id
            next_window = datetime.now(UTC) + timedelta(hours=6)

            await repo.defer(t.id, scheduled_for=next_window)
            await db_session.flush()
            db_session.expire(t)
            reloaded = await repo.find_by_inbox_message(src)
            assert reloaded.status == "pending"
            assert reloaded.scheduled_for is not None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_defer_noop_on_non_processing_row(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            t = await repo.create(_task(tenant_a.org_id, tenant_a.workspace_id, status="pending"))
            await db_session.flush()
            src = t.source_inbox_message_id

            await repo.defer(t.id, scheduled_for=datetime.now(UTC) + timedelta(hours=6))
            await db_session.flush()
            db_session.expire(t)
            reloaded = await repo.find_by_inbox_message(src)
            # Still pending (it was pending, not processing); schedule unchanged (None).
            assert reloaded.status == "pending"
            assert reloaded.scheduled_for is None
        finally:
            clear_tenant_context(token)


# ── reset_stuck_processing (reaper) ──────────────────────────────────────────────

class TestReaper:
    @pytest.mark.asyncio
    async def test_resets_old_processing_leaves_recent(self, db_session, tenant_a):
        token = set_tenant_context(tenant_a)
        await set_rls_tenant(db_session, tenant_a.org_id)
        try:
            repo = FollowUpTaskRepo(db_session)
            now = datetime.now(UTC)
            stuck = await repo.create(
                _task(
                    tenant_a.org_id, tenant_a.workspace_id,
                    status="processing", updated_at=now - timedelta(minutes=20),
                )
            )
            fresh = await repo.create(
                _task(
                    tenant_a.org_id, tenant_a.workspace_id,
                    status="processing", updated_at=now,
                )
            )
            await db_session.flush()
            stuck_src = stuck.source_inbox_message_id
            fresh_src = fresh.source_inbox_message_id

            cutoff = now - timedelta(minutes=10)
            reset_count = await repo.reset_stuck_processing(older_than=cutoff)
            await db_session.flush()
            # >= 1 (not == 1) to stay robust if other tests share the session and
            # left old 'processing' rows; the per-row assertions below are the real
            # verification.
            assert reset_count >= 1

            db_session.expire(stuck)
            db_session.expire(fresh)
            stuck_reloaded = await repo.find_by_inbox_message(stuck_src)
            fresh_reloaded = await repo.find_by_inbox_message(fresh_src)
            assert stuck_reloaded.status == "pending"   # reclaimed
            assert fresh_reloaded.status == "processing"  # left alone
        finally:
            clear_tenant_context(token)
