"""Reporting & Export Center domain events — Sprint 56."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class ReportGenerated:
    report_id: uuid.UUID
    workspace_id: uuid.UUID
    report_type: str
    format: str
    row_count: int
    file_size_bytes: int
    generated_by: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReportDeleted:
    report_id: uuid.UUID
    workspace_id: uuid.UUID
    report_type: str
    deleted_by: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReportFailed:
    report_id: uuid.UUID
    workspace_id: uuid.UUID
    report_type: str
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
