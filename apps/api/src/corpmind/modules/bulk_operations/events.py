"""Bulk Operations domain events — Sprint 59."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class BulkOperationStarted:
    operation_id: uuid.UUID
    workspace_id: uuid.UUID
    operation_type: str
    entity_type: str
    requested_by: uuid.UUID
    total_records: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BulkOperationCompleted:
    operation_id: uuid.UUID
    workspace_id: uuid.UUID
    operation_type: str
    entity_type: str
    total_records: int
    successful_records: int
    failed_records: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BulkOperationFailed:
    operation_id: uuid.UUID
    workspace_id: uuid.UUID
    operation_type: str
    entity_type: str
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CsvValidated:
    workspace_id: uuid.UUID
    entity_type: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    dry_run: bool
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
