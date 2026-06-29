"""Sprint 21 — add recommendation tracking tables.

Revision ID: f4a7e1d9c3b6
Revises: e2b5f8c1a3d6
Create Date: 2026-06-23

New tables (all expand-only — no destructive changes):

  recommendation_snapshots
    One row per (tenant, workspace, rec_type, snapshot_date).
    Written when get_recommendations() computes fresh data on a cache miss.
    Unique constraint enables ON CONFLICT DO UPDATE so re-running is idempotent.
    Preserves confidence_score / confidence_level / title / supporting_data at
    generation time — required for calibration: the score must be frozen as-is,
    not recomputed later when the formula or data may have changed.

  recommendation_feedback
    Explicit trainer feedback: helpful | not_helpful | dismissed.
    One row per (tenant, workspace, snapshot_id) — ON CONFLICT updates outcome
    so trainers can change their mind.
    notes column: free text, Presidio-scrubbed before storage (service layer).

  recommendation_outcomes
    Inferred acted / success flags populated by the daily Celery beat task
    compute_recommendation_outcomes.  Sprint 21 creates the rows; Sprint 22
    fills acted / success for industry / topic / pricing types.
    Channel and campaign types: acted flag detected via campaigns table lookup.

  recommendation_quality_scores
    Daily pre-computed rollup per (tenant, workspace, rec_type).
    Populated by compute_recommendation_quality_scores Celery beat task.
    In Sprint 21 quality_score is driven by feedback only (0-100 or NULL when
    feedback is insufficient).  Sprint 22 adds adoption_rate / success_rate to
    the formula once outcome data accumulates.

RLS: every table has a tenant isolation policy matching the existing pattern.

Reversible: downgrade drops all four tables and their policies in reverse order.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "f4a7e1d9c3b6"
down_revision = "e2b5f8c1a3d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. recommendation_snapshots ─────────────────────────────────────────────
    op.create_table(
        "recommendation_snapshots",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("rec_type", sa.String(30), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_level", sa.String(10), nullable=False, server_default="low"),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("supporting_data", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "rec_type",
            "snapshot_date",
            name="uq_rec_snapshot_tenant_ws_type_date",
        ),
    )
    op.create_index(
        "ix_rec_snapshots_workspace_date",
        "recommendation_snapshots",
        ["tenant_id", "workspace_id", "snapshot_date"],
    )
    op.execute("ALTER TABLE recommendation_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rec_snapshots_tenant_isolation
          ON recommendation_snapshots
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── 2. recommendation_feedback ───────────────────────────────────────────────
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("rec_type", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "snapshot_id",
            name="uq_rec_feedback_tenant_ws_snapshot",
        ),
    )
    op.create_index(
        "ix_rec_feedback_workspace_type",
        "recommendation_feedback",
        ["tenant_id", "workspace_id", "rec_type"],
    )
    op.execute("ALTER TABLE recommendation_feedback ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_feedback FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rec_feedback_tenant_isolation
          ON recommendation_feedback
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── 3. recommendation_outcomes ───────────────────────────────────────────────
    op.create_table(
        "recommendation_outcomes",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("rec_type", sa.String(30), nullable=False),
        sa.Column("acted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_resource_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("success_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_delta", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "snapshot_id",
            name="uq_rec_outcome_tenant_ws_snapshot",
        ),
    )
    op.create_index(
        "ix_rec_outcomes_workspace_type",
        "recommendation_outcomes",
        ["tenant_id", "workspace_id", "rec_type"],
    )
    op.execute("ALTER TABLE recommendation_outcomes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_outcomes FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rec_outcomes_tenant_isolation
          ON recommendation_outcomes
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )

    # ── 4. recommendation_quality_scores ────────────────────────────────────────
    op.create_table(
        "recommendation_quality_scores",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("rec_type", sa.String(30), nullable=False),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("shown_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("acted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ignored_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback_helpful", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback_not_helpful", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback_dismissed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("adoption_rate", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("low_confidence", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "rec_type",
            "score_date",
            name="uq_rec_quality_tenant_ws_type_date",
        ),
    )
    op.create_index(
        "ix_rec_quality_workspace_date",
        "recommendation_quality_scores",
        ["tenant_id", "workspace_id", "score_date"],
    )
    op.execute("ALTER TABLE recommendation_quality_scores ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_quality_scores FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rec_quality_scores_tenant_isolation
          ON recommendation_quality_scores
          USING (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )


def downgrade() -> None:
    # Drop in reverse creation order (quality → outcomes → feedback → snapshots)
    op.execute(
        "DROP POLICY IF EXISTS rec_quality_scores_tenant_isolation "
        "ON recommendation_quality_scores"
    )
    op.drop_index("ix_rec_quality_workspace_date", table_name="recommendation_quality_scores")
    op.drop_table("recommendation_quality_scores")

    op.execute(
        "DROP POLICY IF EXISTS rec_outcomes_tenant_isolation ON recommendation_outcomes"
    )
    op.drop_index("ix_rec_outcomes_workspace_type", table_name="recommendation_outcomes")
    op.drop_table("recommendation_outcomes")

    op.execute(
        "DROP POLICY IF EXISTS rec_feedback_tenant_isolation ON recommendation_feedback"
    )
    op.drop_index("ix_rec_feedback_workspace_type", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")

    op.execute(
        "DROP POLICY IF EXISTS rec_snapshots_tenant_isolation ON recommendation_snapshots"
    )
    op.drop_index("ix_rec_snapshots_workspace_date", table_name="recommendation_snapshots")
    op.drop_table("recommendation_snapshots")
