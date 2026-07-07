"""Audit module schemas — Sprint 53."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

AUDIT_SEVERITIES: frozenset[str] = frozenset({"info", "warning", "critical"})


class AuditLogCreate(BaseModel):
    """Internal-only schema.  Not exposed via a public POST endpoint."""

    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action: str
    module: str
    severity: str = "info"
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    action: str
    module: str
    severity: str
    ip_address: str | None
    user_agent: str | None
    # ORM stores this as `extra_data`; API surfaces it as `metadata`.
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("extra_data", "metadata"),
    )
    created_at: datetime


class AuditLogFilters(BaseModel):
    workspace_id: uuid.UUID
    module: str | None = None
    severity: str | None = None
    user_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    next_cursor: str | None
    has_more: bool
    total: int


class AuditStatisticsOut(BaseModel):
    total_events: int
    by_severity: dict[str, int]
    by_module: dict[str, int]
    by_action: dict[str, int]
    period_days: int
