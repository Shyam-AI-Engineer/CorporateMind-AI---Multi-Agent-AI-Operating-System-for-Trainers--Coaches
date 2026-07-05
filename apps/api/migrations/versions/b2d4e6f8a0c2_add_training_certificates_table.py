"""add training_certificates table — Sprint 45.

Revision ID: b2d4e6f8a0c2
Revises: a5b9c3d7e1f4
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b2d4e6f8a0c2"
down_revision = "a5b9c3d7e1f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_certificates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("certificate_number", sa.String(100), nullable=True),
        sa.Column("participant_name", sa.String(255), nullable=False),
        sa.Column("participant_email", sa.String(255), nullable=True),
        sa.Column("certificate_title", sa.String(500), nullable=True),
        sa.Column("issue_date", sa.Date, nullable=True),
        sa.Column("issued_by", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "download_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column("verification_code", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_training_certificates_tenant_workspace",
        "training_certificates",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_training_certificates_attendance_id",
        "training_certificates",
        ["attendance_id"],
    )
    op.create_index(
        "ix_training_certificates_session_id",
        "training_certificates",
        ["session_id"],
    )
    op.create_index(
        "ix_training_certificates_certificate_number",
        "training_certificates",
        ["certificate_number"],
    )
    op.create_index(
        "ix_training_certificates_verification_code",
        "training_certificates",
        ["verification_code"],
        unique=True,
    )
    op.create_index(
        "ix_training_certificates_status",
        "training_certificates",
        ["status"],
    )
    # Keyset pagination index
    op.create_index(
        "ix_training_certificates_created_id",
        "training_certificates",
        ["created_at", "id"],
    )

    op.execute("ALTER TABLE training_certificates ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY training_certificates_tenant_isolation
        ON training_certificates
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
    """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS training_certificates_tenant_isolation ON training_certificates"
    )
    op.drop_index(
        "ix_training_certificates_created_id",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_status",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_verification_code",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_certificate_number",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_session_id",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_attendance_id",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_tenant_workspace",
        table_name="training_certificates",
    )
    op.drop_table("training_certificates")
