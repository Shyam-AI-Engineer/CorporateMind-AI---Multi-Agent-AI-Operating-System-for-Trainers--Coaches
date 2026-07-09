"""Reporting & Export Center schemas — Sprint 56."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_REPORT_TYPES: frozenset[str] = frozenset(
    {
        "customers",
        "training",
        "invoices",
        "payments",
        "executive_kpis",
        "workflow_analytics",
        "audit_logs",
    }
)

SUPPORTED_FORMATS: frozenset[str] = frozenset({"csv", "xlsx"})


# ── Request schemas ───────────────────────────────────────────────────────────


class GenerateReportRequest(BaseModel):
    workspace_id: uuid.UUID
    report_type: str
    format: str
    # Optional date filters (ISO date strings)
    date_from: str | None = None
    date_to: str | None = None

    @field_validator("report_type")
    @classmethod
    def validate_report_type(cls, v: str) -> str:
        if v not in SUPPORTED_REPORT_TYPES:
            raise ValueError(
                f"Unsupported report_type '{v}'. "
                f"Valid: {sorted(SUPPORTED_REPORT_TYPES)}"
            )
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{v}'. Valid: {sorted(SUPPORTED_FORMATS)}"
            )
        return v


# ── Output schemas ────────────────────────────────────────────────────────────


class ReportExportOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    report_type: str
    format: str
    status: str
    generated_by: uuid.UUID
    generated_at: datetime | None
    download_name: str | None
    row_count: int | None
    file_size_bytes: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportExportListOut(BaseModel):
    items: list[ReportExportOut]
    total: int
