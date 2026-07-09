"""Security Center output schemas — Sprint 58.

All schemas are read-only DTOs derived from existing tables.
No migration required — all data comes from workspace_members, api_keys, audit_logs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class SecuritySummaryOut(BaseModel):
    """Aggregate security posture snapshot."""

    model_config = {"from_attributes": True}

    overall_security_score: float
    active_api_keys: int
    expired_api_keys: int
    active_workspace_members: int
    organization_admins: int
    audit_events_today: int
    critical_audit_events: int
    checked_at: datetime

    @field_validator("overall_security_score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class RoleCount(BaseModel):
    """Member count for a single role."""

    model_config = {"from_attributes": True}

    role: str
    count: int


class RoleDistributionOut(BaseModel):
    """Workspace member counts grouped by role."""

    model_config = {"from_attributes": True}

    roles: list[RoleCount]
    total_members: int
    checked_at: datetime


class ApiKeyHealthOut(BaseModel):
    """API key lifecycle health indicators."""

    model_config = {"from_attributes": True}

    total_keys: int
    active: int
    expired: int
    never_used: int
    used_last_30_days: int
    checked_at: datetime


class ModuleAuditEntry(BaseModel):
    """Audit event count for a single module."""

    model_config = {"from_attributes": True}

    module: str
    event_count: int


class AuditSummaryOut(BaseModel):
    """Audit log summary for today."""

    model_config = {"from_attributes": True}

    events_today: int
    critical_events: int
    warning_events: int
    top_modules: list[ModuleAuditEntry]
    checked_at: datetime


class WorkspacePermissionRow(BaseModel):
    """Role distribution for one workspace."""

    model_config = {"from_attributes": True}

    workspace_id: str
    owners: int
    admins: int
    members: int
    viewers: int


class PermissionOverviewOut(BaseModel):
    """Per-workspace role distribution overview."""

    model_config = {"from_attributes": True}

    workspaces: list[WorkspacePermissionRow]
    total_workspaces: int
    checked_at: datetime


class SecurityAlert(BaseModel):
    """A single rule-based security alert."""

    model_config = {"from_attributes": True}

    alert_type: str
    severity: str  # low | medium | high | critical
    message: str
    count: int


class SecurityAlertsOut(BaseModel):
    """Deterministic rule-based security alerts (cached 5 min)."""

    model_config = {"from_attributes": True}

    alerts: list[SecurityAlert]
    total: int
    checked_at: datetime
