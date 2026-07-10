"""Bulk Operations schemas — Sprint 59."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_ENTITY_TYPES = frozenset(
    {"customers", "training_engagements", "business_tasks", "workflow_templates"}
)
SUPPORTED_OPERATION_TYPES = frozenset(
    {
        "csv_import",
        "csv_validate",
        "bulk_archive",
        "bulk_status_update",
        "bulk_assignment",
        "dry_run",
    }
)
OPERATION_STATUSES = frozenset(
    {"pending", "running", "completed", "failed", "cancelled"}
)
MAX_BATCH_SIZE = 1000
MAX_CSV_ROWS = 5000


# ── Row-level validation result ────────────────────────────────────────────────

class RowValidationError(BaseModel):
    row: int
    field: str
    message: str


class ValidationRowResult(BaseModel):
    row: int
    valid: bool
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[RowValidationError] = Field(default_factory=list)


# ── Request bodies ─────────────────────────────────────────────────────────────

class CsvValidateRequest(BaseModel):
    workspace_id: uuid.UUID
    entity_type: str
    rows: list[dict[str, Any]] = Field(..., min_length=1)
    dry_run: bool = False

    @field_validator("entity_type")
    @classmethod
    def entity_type_valid(cls, v: str) -> str:
        if v not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(SUPPORTED_ENTITY_TYPES)}")
        return v

    @field_validator("rows")
    @classmethod
    def rows_within_limit(cls, v: list) -> list:
        if len(v) > MAX_CSV_ROWS:
            raise ValueError(f"rows must not exceed {MAX_CSV_ROWS}")
        return v


class CsvImportRequest(BaseModel):
    workspace_id: uuid.UUID
    entity_type: str
    rows: list[dict[str, Any]] = Field(..., min_length=1)
    requested_by: uuid.UUID
    stop_on_error: bool = False

    @field_validator("entity_type")
    @classmethod
    def entity_type_valid(cls, v: str) -> str:
        if v not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(SUPPORTED_ENTITY_TYPES)}")
        return v

    @field_validator("rows")
    @classmethod
    def rows_within_limit(cls, v: list) -> list:
        if len(v) > MAX_CSV_ROWS:
            raise ValueError(f"rows must not exceed {MAX_CSV_ROWS}")
        return v


class BulkArchiveRequest(BaseModel):
    workspace_id: uuid.UUID
    entity_type: str
    entity_ids: list[uuid.UUID] = Field(..., min_length=1)
    requested_by: uuid.UUID

    @field_validator("entity_type")
    @classmethod
    def entity_type_valid(cls, v: str) -> str:
        if v not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(SUPPORTED_ENTITY_TYPES)}")
        return v

    @field_validator("entity_ids")
    @classmethod
    def ids_within_limit(cls, v: list) -> list:
        if len(v) > MAX_BATCH_SIZE:
            raise ValueError(f"entity_ids must not exceed {MAX_BATCH_SIZE}")
        return v


class BulkAssignRequest(BaseModel):
    workspace_id: uuid.UUID
    entity_type: str
    entity_ids: list[uuid.UUID] = Field(..., min_length=1)
    assignee_id: uuid.UUID
    requested_by: uuid.UUID

    @field_validator("entity_type")
    @classmethod
    def entity_type_valid(cls, v: str) -> str:
        if v not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(SUPPORTED_ENTITY_TYPES)}")
        return v

    @field_validator("entity_ids")
    @classmethod
    def ids_within_limit(cls, v: list) -> list:
        if len(v) > MAX_BATCH_SIZE:
            raise ValueError(f"entity_ids must not exceed {MAX_BATCH_SIZE}")
        return v


class BulkStatusUpdateRequest(BaseModel):
    workspace_id: uuid.UUID
    entity_type: str
    entity_ids: list[uuid.UUID] = Field(..., min_length=1)
    new_status: str
    requested_by: uuid.UUID

    @field_validator("entity_type")
    @classmethod
    def entity_type_valid(cls, v: str) -> str:
        if v not in SUPPORTED_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(SUPPORTED_ENTITY_TYPES)}")
        return v

    @field_validator("entity_ids")
    @classmethod
    def ids_within_limit(cls, v: list) -> list:
        if len(v) > MAX_BATCH_SIZE:
            raise ValueError(f"entity_ids must not exceed {MAX_BATCH_SIZE}")
        return v


class ListOperationsRequest(BaseModel):
    workspace_id: uuid.UUID
    entity_type: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)


# ── Response schemas ───────────────────────────────────────────────────────────

class BulkOperationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    operation_type: str
    entity_type: str
    status: str
    requested_by: uuid.UUID
    total_records: int
    processed_records: int
    successful_records: int
    failed_records: int
    started_at: datetime
    completed_at: Optional[datetime]
    error_summary: Optional[str]
    created_at: datetime


class CsvValidationOut(BaseModel):
    entity_type: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    dry_run: bool
    results: list[ValidationRowResult]


class BulkOperationListOut(BaseModel):
    operations: list[BulkOperationOut]
    total: int
