"""Add CRM automation tables: activities, follow-up tasks, automation log.

Revision ID: b9c5d3e2f7a4
Revises: a8b2c9d4e6f1
Create Date: 2026-06-09

Three new tables introduced by Sprint 4C (CRM Automation from Classified Replies):

crm_activities
  Append-only activity log per lead.  Every reply automation writes one row so
  the timeline view can show "interested reply → advanced to engaged" without
  joining across modules at read time.  source_inbox_message_id links back to
  the trigger and is indexed; lead_id may be NULL for activities tied to a
  contact but no live lead (e.g. bounce on a contact without an active lead).

follow_up_tasks
  Plain task rows for `question` (immediate follow-up) and `out_of_office`
  (scheduled follow-up).  No scheduler wiring this sprint — Sprint 4D+ will
  consume these.  UNIQUE(tenant_id, source_inbox_message_id) gives second-line
  idempotency in addition to the automation log.

inbox_message_automation_log
  Single source of truth for "this inbox_message has had automation applied".
  ReplyAutomationService inserts ON CONFLICT DO NOTHING; a False return path
  causes the automation to short-circuit.  This protects against duplicate
  processing from worker retries, beat overlaps, or future event-bus replay.

RLS: all three follow the hardened NULLIF predicate from b9f4e7d2a1c8.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c5d3e2f7a4"
down_revision = "a8b2c9d4e6f1"
branch_labels = None
depends_on = None

_PREDICATE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table}"
        f"  USING ({_PREDICATE})"
        f"  WITH CHECK ({_PREDICATE})"
    )


def _disable_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    # ── crm_activities ────────────────────────────────────────────────────────
    op.create_table(
        "crm_activities",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        # Activity type — vocabulary controlled application-side:
        # lead_engaged | lead_cold | followup_required | followup_scheduled
        # | contact_bounced | auto_reply_logged | unknown_intent_logged
        # | automation_failed | automation_skipped
        sa.Column("type", sa.String(length=50), nullable=False),
        # Free-form short summary shown in the timeline view.
        sa.Column("summary", sa.Text(), nullable=False),
        # Which inbound triggered this activity — link back to inbox_messages.
        # Indexed because the timeline view filters by it.
        sa.Column("source_inbox_message_id", sa.UUID(), nullable=True),
        sa.Column("source_outbound_message_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_activities_tenant_id"), "crm_activities", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_crm_activities_lead_id"), "crm_activities", ["lead_id"]
    )
    op.create_index(
        op.f("ix_crm_activities_contact_id"), "crm_activities", ["contact_id"]
    )
    op.create_index(
        op.f("ix_crm_activities_source_inbox_message_id"),
        "crm_activities",
        ["source_inbox_message_id"],
    )
    _enable_rls("crm_activities")

    # ── follow_up_tasks ───────────────────────────────────────────────────────
    op.create_table(
        "follow_up_tasks",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        # Type — application-controlled vocabulary:
        # question_followup | out_of_office_followup
        sa.Column("type", sa.String(length=50), nullable=False),
        # Lifecycle: pending | done | cancelled
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # NULL ⇒ "do as soon as possible" (used for `question` intent).
        # Populated ⇒ scheduled in the future (used for `out_of_office`).
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_inbox_message_id", sa.UUID(), nullable=False),
        sa.Column("source_outbound_message_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        # Second-line idempotency: even if the automation log gate is bypassed,
        # the same inbox message cannot spawn two follow-ups.
        sa.UniqueConstraint(
            "tenant_id",
            "source_inbox_message_id",
            name="uq_follow_up_tasks_tenant_source",
        ),
    )
    op.create_index(
        op.f("ix_follow_up_tasks_tenant_id"), "follow_up_tasks", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_follow_up_tasks_lead_id"), "follow_up_tasks", ["lead_id"]
    )
    op.create_index(
        op.f("ix_follow_up_tasks_status"), "follow_up_tasks", ["status"]
    )
    op.create_index(
        op.f("ix_follow_up_tasks_scheduled_for"),
        "follow_up_tasks",
        ["scheduled_for"],
    )
    _enable_rls("follow_up_tasks")

    # ── inbox_message_automation_log ──────────────────────────────────────────
    # The PRIMARY idempotency mechanism.  ReplyAutomationService inserts here
    # before any CRM mutation; ON CONFLICT DO NOTHING returns 0 rowcount and
    # the automation short-circuits.  No FK to inbox_messages so deleting an
    # inbox row does not nuke the idempotency record (deletion is rare; the
    # automation history is more durable than the source message).
    op.create_table(
        "inbox_message_automation_log",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("inbox_message_id", sa.UUID(), nullable=False),
        # Outcome: applied | failed | skipped
        sa.Column("outcome", sa.String(length=30), nullable=False),
        # Intent that was processed — captured for forensic queries.
        sa.Column("intent", sa.String(length=50), nullable=False),
        # Short categorised reason when outcome != applied.
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "inbox_message_id",
            name="uq_inbox_message_automation_log_tenant_msg",
        ),
    )
    op.create_index(
        op.f("ix_inbox_message_automation_log_tenant_id"),
        "inbox_message_automation_log",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_inbox_message_automation_log_inbox_message_id"),
        "inbox_message_automation_log",
        ["inbox_message_id"],
    )
    _enable_rls("inbox_message_automation_log")


def downgrade() -> None:
    _disable_rls("inbox_message_automation_log")
    op.drop_index(
        op.f("ix_inbox_message_automation_log_inbox_message_id"),
        table_name="inbox_message_automation_log",
    )
    op.drop_index(
        op.f("ix_inbox_message_automation_log_tenant_id"),
        table_name="inbox_message_automation_log",
    )
    op.drop_table("inbox_message_automation_log")

    _disable_rls("follow_up_tasks")
    op.drop_index(
        op.f("ix_follow_up_tasks_scheduled_for"), table_name="follow_up_tasks"
    )
    op.drop_index(op.f("ix_follow_up_tasks_status"), table_name="follow_up_tasks")
    op.drop_index(op.f("ix_follow_up_tasks_lead_id"), table_name="follow_up_tasks")
    op.drop_index(op.f("ix_follow_up_tasks_tenant_id"), table_name="follow_up_tasks")
    op.drop_table("follow_up_tasks")

    _disable_rls("crm_activities")
    op.drop_index(
        op.f("ix_crm_activities_source_inbox_message_id"),
        table_name="crm_activities",
    )
    op.drop_index(op.f("ix_crm_activities_contact_id"), table_name="crm_activities")
    op.drop_index(op.f("ix_crm_activities_lead_id"), table_name="crm_activities")
    op.drop_index(op.f("ix_crm_activities_tenant_id"), table_name="crm_activities")
    op.drop_table("crm_activities")
