"""Reporting & Export Center models — Sprint 56."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class ReportExport(TenantBase):
    """Metadata record for a generated report export.

    The actual file bytes live in configured storage; this table tracks
    only the metadata so tenants can browse and re-download their history.
    """

    __tablename__ = "report_exports"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # e.g. "customers", "training", "invoices", "payments", "executive_kpis",
    #       "workflow_analytics", "audit_logs"
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)  # "csv" | "xlsx"
    # "pending" | "ready" | "failed"
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    generated_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    download_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
