"""Admin module Pydantic schemas — Sprint 54: Organization Administration Center."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"INR", "USD", "EUR", "GBP", "SGD", "AED"})
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "hi", "ta", "bn", "mr", "te", "kn", "gu"})
SUPPORTED_DATE_FORMATS: frozenset[str] = frozenset({"DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"})

# Known module names for system status reporting
MODULE_NAMES: list[str] = [
    "customers",
    "training",
    "billing",
    "payments",
    "notifications",
    "audit",
    "workflow",
    "team",
]


# ── Settings schemas ───────────────────────────────────────────────────────────

class OrganizationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    organization_name: str
    timezone: str
    currency: str
    date_format: str
    language: str
    default_workflow_id: uuid.UUID | None
    default_training_duration_days: int
    default_invoice_due_days: int
    logo_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationSettingsUpdate(BaseModel):
    organization_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, max_length=8)
    date_format: str | None = Field(default=None, max_length=32)
    language: str | None = Field(default=None, max_length=16)
    default_workflow_id: uuid.UUID | None = None
    default_training_duration_days: int | None = Field(default=None, ge=1, le=365)
    default_invoice_due_days: int | None = Field(default=None, ge=1, le=365)
    logo_url: str | None = Field(default=None, max_length=2048)


# ── Dashboard / module schemas ─────────────────────────────────────────────────

class ModuleStatusOut(BaseModel):
    name: str
    enabled: bool
    healthy: bool
    record_count: int


class SystemStatusOut(BaseModel):
    modules: list[ModuleStatusOut]
    overall_healthy: bool
    checked_at: datetime


class AdminDashboardOut(BaseModel):
    organization_name: str
    tenant_id: uuid.UUID
    is_active: bool
    module_count: int
    healthy_module_count: int
    total_records: int
    settings_last_updated: datetime
    system_status: SystemStatusOut


class AdminModuleListOut(BaseModel):
    modules: list[str]
    total: int
