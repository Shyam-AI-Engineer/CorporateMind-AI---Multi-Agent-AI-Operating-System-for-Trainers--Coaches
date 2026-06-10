"""Integration tests for ReplyAutomationService against a real PostgreSQL.

What this file proves (and what the unit-test file cannot):
  - The automation log UNIQUE(tenant_id, inbox_message_id) constraint actually
    fires under concurrent simulated retries.
  - CRM lead stage transitions persist through SQLAlchemy + RLS.
  - HRContact.email_deliverable=False is written via the cross-module raw-SQL
    update path.
  - Activity rows and FollowUpTask rows are written and visible.
  - Cross-tenant isolation: tenant B cannot see tenant A's activities / tasks.

Conventions mirrored from test_inbox_service_integration.py:
  - SET app.tenant_id at SESSION level (not LOCAL) — InboxService + CRMService
    both commit internally, and SET LOCAL would reset on each commit.
  - NullPool seeding when we need to bypass RLS to plant fixtures.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from corpmind.core.tenancy import clear_tenant_context, set_tenant_context
from corpmind.modules.crm.automation import ReplyAutomationService
from corpmind.modules.crm.models import Activity, FollowUpTask, Lead
from corpmind.modules.crm.repo import (
    ActivityRepo,
    AutomationLogRepo,
    FollowUpTaskRepo,
    LeadRepo,
)


# ── Session-level RLS helper ──────────────────────────────────────────────────

async def _rls(session, tenant_id: uuid.UUID) -> None:
    """Match the SET (not SET LOCAL) pattern used in test_inbox_service_integration."""
    await session.execute(text(f"SET app.tenant_id = '{tenant_id}'"))


# ── Fixture seeding helpers ───────────────────────────────────────────────────

async def _seed_outbound_and_contact(
    db_engine,
    *,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID,
    workspace_id: uuid.UUID,
    outbound_id: uuid.UUID,
) -> None:
    """Seed an hr_contacts + outbound_messages row under tenant_id (bypassing RLS).

    The automation pipeline needs both:
      - outbound_messages row → _resolve_outbound returns (contact_id, workspace_id)
      - hr_contacts row → bounce can update email_deliverable
    """
    company_id = uuid.uuid4()
    seed_engine = create_async_engine(
        db_engine.url.render_as_string(hide_password=False), poolclass=NullPool
    )
    try:
        async with seed_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO companies (id, tenant_id, name, extra)"
                    " VALUES (:cid, :tid, 'TestCo', '{}'::jsonb)"
                ),
                {"cid": str(company_id), "tid": str(tenant_id)},
            )
            await conn.execute(
                text(
                    "INSERT INTO hr_contacts"
                    " (id, tenant_id, company_id, full_name, email,"
                    "  email_deliverable, source, source_type, is_contactable)"
                    " VALUES (:cid, :tid, :coid, 'Test Contact', 'x@y.com',"
                    "         true, 'test', 'test', true)"
                ),
                {
                    "cid": str(contact_id),
                    "tid": str(tenant_id),
                    "coid": str(company_id),
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO outbound_messages"
                    " (id, tenant_id, contact_id, channel, body, status)"
                    " VALUES (:id, :tid, :cid, 'email', 'Test', 'sent')"
                ),
                {
                    "id": str(outbound_id),
                    "tid": str(tenant_id),
                    "cid": str(contact_id),
                },
            )
    finally:
        await seed_engine.dispose()


async def _seed_lead(
    session, *, tenant_id: uuid.UUID, contact_id: uuid.UUID, workspace_id: uuid.UUID,
    stage: str = "discovered",
) -> Lead:
    lead = Lead(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        contact_id=contact_id,
        stage=stage,
    )
    session.add(lead)
    await session.flush()
    await session.commit()
    return lead


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAutomationCRMPersistence:
    @pytest.mark.asyncio
    async def test_interested_advances_lead_in_db(
        self, db_engine, db_session, tenant_a
    ):
        """Full round-trip: interested intent → lead.stage = 'engaged' in DB."""
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            lead = await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            result = await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="interested",
                outbound_message_id=outbound_id,
            )
            assert result.outcome == "applied"

            # Lead.stage should now be 'engaged'.
            await _rls(db_session, tenant_a.org_id)
            refreshed = await LeadRepo(db_session).find_by_id(lead.id)
            assert refreshed is not None
            assert refreshed.stage == "engaged"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_activity_row_persisted(self, db_engine, db_session, tenant_a):
        """Every applied automation writes one crm_activities row."""
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="interested",
                outbound_message_id=outbound_id,
            )

            await _rls(db_session, tenant_a.org_id)
            activity = await ActivityRepo(db_session).find_by_inbox_message(
                inbox_message_id
            )
            assert activity is not None
            assert activity.type == "lead_engaged"
            assert activity.contact_id == contact_id
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_question_creates_followup_task(
        self, db_engine, db_session, tenant_a
    ):
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="question",
                outbound_message_id=outbound_id,
            )

            await _rls(db_session, tenant_a.org_id)
            task = await FollowUpTaskRepo(db_session).find_by_inbox_message(
                inbox_message_id
            )
            assert task is not None
            assert task.type == "question_followup"
            assert task.status == "pending"
            assert task.scheduled_for is None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_out_of_office_creates_scheduled_followup(
        self, db_engine, db_session, tenant_a
    ):
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="out_of_office",
                outbound_message_id=outbound_id,
            )

            await _rls(db_session, tenant_a.org_id)
            task = await FollowUpTaskRepo(db_session).find_by_inbox_message(
                inbox_message_id
            )
            assert task is not None
            assert task.type == "out_of_office_followup"
            assert task.scheduled_for is not None
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_bounce_marks_contact_undeliverable(
        self, db_engine, db_session, tenant_a
    ):
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            result = await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="bounce",
                outbound_message_id=outbound_id,
            )
            assert result.outcome == "applied"

            # Verify hr_contacts.email_deliverable is now False
            await _rls(db_session, tenant_a.org_id)
            row = await db_session.execute(
                text(
                    "SELECT email_deliverable FROM hr_contacts WHERE id = :cid"
                ),
                {"cid": str(contact_id)},
            )
            value = row.scalar_one()
            assert value is False
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_not_interested_marks_lead_lost(
        self, db_engine, db_session, tenant_a
    ):
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            lead = await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
                stage="engaged",
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="not_interested",
                outbound_message_id=outbound_id,
            )

            await _rls(db_session, tenant_a.org_id)
            refreshed = await LeadRepo(db_session).find_by_id(lead.id)
            assert refreshed is not None
            assert refreshed.stage == "lost"
        finally:
            clear_tenant_context(token)


# ── Idempotency (real UNIQUE constraint) ──────────────────────────────────────

class TestAutomationIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_sync_no_double_advance(
        self, db_engine, db_session, tenant_a
    ):
        """Two handle_classified calls with the same inbox_message_id must
        leave the lead in stage='engaged' (not advanced twice).

        This exercises the real UNIQUE(tenant_id, inbox_message_id) constraint
        on inbox_message_automation_log.
        """
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            lead = await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            first = await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="interested",
                outbound_message_id=outbound_id,
            )
            assert first.outcome == "applied"

            # Second call — same inbox_message_id
            await _rls(db_session, tenant_a.org_id)
            second = await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="interested",
                outbound_message_id=outbound_id,
            )
            assert second.outcome == "already_applied"

            # Lead must still be in engaged (NOT meeting_scheduled)
            await _rls(db_session, tenant_a.org_id)
            refreshed = await LeadRepo(db_session).find_by_id(lead.id)
            assert refreshed is not None
            assert refreshed.stage == "engaged"
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_duplicate_question_no_double_task(
        self, db_engine, db_session, tenant_a
    ):
        """Same idempotency for follow-up tasks — UNIQUE(tenant_id, source_inbox_message_id)
        on follow_up_tasks would catch it, but the automation log gate fires first."""
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="question",
                outbound_message_id=outbound_id,
            )
            await _rls(db_session, tenant_a.org_id)
            second = await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="question",
                outbound_message_id=outbound_id,
            )
            assert second.outcome == "already_applied"

            # Exactly one row in follow_up_tasks for this inbox_message
            await _rls(db_session, tenant_a.org_id)
            count_row = await db_session.execute(
                text(
                    "SELECT count(*) FROM follow_up_tasks"
                    " WHERE source_inbox_message_id = :iid"
                ),
                {"iid": str(inbox_message_id)},
            )
            assert count_row.scalar_one() == 1
        finally:
            clear_tenant_context(token)

    @pytest.mark.asyncio
    async def test_automation_log_row_persisted(
        self, db_engine, db_session, tenant_a
    ):
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            await _seed_lead(
                db_session,
                tenant_id=tenant_a.org_id,
                contact_id=contact_id,
                workspace_id=tenant_a.workspace_id,
            )

            await _rls(db_session, tenant_a.org_id)
            svc = ReplyAutomationService(db_session)
            await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="interested",
                outbound_message_id=outbound_id,
            )

            await _rls(db_session, tenant_a.org_id)
            row = await AutomationLogRepo(db_session).find_by_inbox_message(
                inbox_message_id
            )
            assert row is not None
            assert row.outcome == "applied"
            assert row.intent == "interested"
        finally:
            clear_tenant_context(token)


# ── Validation gate persistence ───────────────────────────────────────────────

class TestAutomationFailureGates:
    @pytest.mark.asyncio
    async def test_no_outbound_match_writes_failed_log_and_no_activity(
        self, db_session, tenant_a
    ):
        inbox_message_id = uuid.uuid4()
        token = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        try:
            svc = ReplyAutomationService(db_session)
            result = await svc.handle_classified(
                inbox_message_id=inbox_message_id,
                tenant_id=tenant_a.org_id,
                intent="interested",
                outbound_message_id=None,
            )
            assert result.outcome == "failed"
            assert result.reason == "no_outbound_match"

            # Automation log row exists with outcome=applied (the reservation
            # we made before validation) — this is intentional: a duplicate
            # retry must not re-process the same gate failure.
            await _rls(db_session, tenant_a.org_id)
            row = await AutomationLogRepo(db_session).find_by_inbox_message(
                inbox_message_id
            )
            assert row is not None
        finally:
            clear_tenant_context(token)


# ── Tenant isolation ──────────────────────────────────────────────────────────

class TestAutomationTenantIsolation:
    @pytest.mark.asyncio
    async def test_activity_invisible_across_tenants(
        self, db_engine, db_session, tenant_a, tenant_b
    ):
        """Activities written under tenant A must not be visible to tenant B."""
        contact_id = uuid.uuid4()
        outbound_id = uuid.uuid4()
        inbox_message_id = uuid.uuid4()
        await _seed_outbound_and_contact(
            db_engine,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
            outbound_id=outbound_id,
        )

        # Apply automation as tenant A
        token_a = set_tenant_context(tenant_a)
        await _rls(db_session, tenant_a.org_id)
        await _seed_lead(
            db_session,
            tenant_id=tenant_a.org_id,
            contact_id=contact_id,
            workspace_id=tenant_a.workspace_id,
        )
        await _rls(db_session, tenant_a.org_id)
        await ReplyAutomationService(db_session).handle_classified(
            inbox_message_id=inbox_message_id,
            tenant_id=tenant_a.org_id,
            intent="interested",
            outbound_message_id=outbound_id,
        )
        clear_tenant_context(token_a)

        # As tenant B, the activity is invisible
        token_b = set_tenant_context(tenant_b)
        await _rls(db_session, tenant_b.org_id)
        try:
            invisible = await ActivityRepo(db_session).find_by_inbox_message(
                inbox_message_id
            )
            assert invisible is None
        finally:
            clear_tenant_context(token_b)
