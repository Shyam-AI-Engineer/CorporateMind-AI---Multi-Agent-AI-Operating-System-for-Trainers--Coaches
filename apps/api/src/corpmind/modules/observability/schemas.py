"""Observability & Diagnostics response schemas — Sprint 57.

All schemas are read-only output models; no input mutations.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Platform Summary ──────────────────────────────────────────────────────────


class PlatformSummaryOut(BaseModel):
    """Aggregate health snapshot across all platform layers."""

    overall_health_score: float = Field(
        ge=0.0, le=1.0, description="0.0 = fully degraded, 1.0 = fully healthy"
    )
    api_health: str = Field(description="healthy | degraded | down")
    database_health: str = Field(description="healthy | degraded | down")
    cache_health: str = Field(description="healthy | degraded | down")
    storage_health: str = Field(description="healthy | degraded | down")
    active_modules: int
    healthy_modules: int
    warning_modules: int
    checked_at: datetime

    model_config = {"from_attributes": True}


# ── Cache Health ──────────────────────────────────────────────────────────────


class CacheHealthOut(BaseModel):
    """Redis cache diagnostics."""

    redis_available: bool
    estimated_hit_ratio: float = Field(ge=0.0, le=1.0)
    estimated_miss_ratio: float = Field(ge=0.0, le=1.0)
    ttl_configuration: dict[str, int] = Field(
        description="Known TTL values in seconds keyed by cache purpose"
    )
    checked_at: datetime

    model_config = {"from_attributes": True}


# ── Database Health ───────────────────────────────────────────────────────────


class DatabaseHealthOut(BaseModel):
    """PostgreSQL connection and schema diagnostics."""

    connection_ok: bool
    estimated_latency_ms: float
    table_count: int
    migration_version: str
    checked_at: datetime

    model_config = {"from_attributes": True}


# ── API Health ────────────────────────────────────────────────────────────────


class ApiHealthOut(BaseModel):
    """FastAPI route and error-rate diagnostics."""

    registered_routes: int
    average_response_bucket: str = Field(description="fast | moderate | slow")
    error_rate: float = Field(
        ge=0.0, le=1.0,
        description="Fraction of recent critical audit events to total events (last 24h)"
    )
    checked_at: datetime

    model_config = {"from_attributes": True}


# ── Module Health ─────────────────────────────────────────────────────────────


class ModuleHealthItem(BaseModel):
    """Health row for a single business module."""

    module: str
    healthy: bool
    enabled: bool
    record_count: int
    cache_enabled: bool
    checked_at: datetime

    model_config = {"from_attributes": True}


class ModuleHealthOut(BaseModel):
    """Aggregate module health across all 12 tracked modules."""

    modules: list[ModuleHealthItem]
    total: int
    healthy: int
    warning: int

    model_config = {"from_attributes": True}


# ── Recent Errors ─────────────────────────────────────────────────────────────


class RecentErrorItem(BaseModel):
    """Single diagnostic event from recent audit logs."""

    source: str = Field(description="Module that raised the event")
    message: str = Field(description="Audit action / event name")
    severity: str = Field(description="warning | critical")
    occurred_at: datetime

    model_config = {"from_attributes": True}


class RecentErrorsOut(BaseModel):
    """Recent warning/critical events from audit_logs (last 24h, max 50)."""

    errors: list[RecentErrorItem]
    total: int
    checked_at: datetime

    model_config = {"from_attributes": True}
