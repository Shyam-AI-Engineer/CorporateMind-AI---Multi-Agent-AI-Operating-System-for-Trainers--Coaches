"""Workflow Templates & Playbooks schemas — Sprint 33."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

_VALID_CATEGORIES: frozenset[str] = frozenset({
    "new_corporate_lead",
    "proposal_review",
    "enterprise_sales",
    "training_delivery",
    "customer_followup",
    "renewal_process",
    "onboarding",
    "other",
})

_VALID_OWNER_ROLES: frozenset[str] = frozenset({"owner", "admin", "member", "viewer"})


# ── Input schemas ─────────────────────────────────────────────────────────────

class WorkflowTemplateIn(BaseModel):
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    category: str
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        if len(v) > 255:
            raise ValueError("name cannot exceed 255 characters")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in _VALID_CATEGORIES:
            raise ValueError(
                f"category must be one of {sorted(_VALID_CATEGORIES)}"
            )
        return v


class WorkflowTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        if len(v) > 255:
            raise ValueError("name cannot exceed 255 characters")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _VALID_CATEGORIES:
            raise ValueError(
                f"category must be one of {sorted(_VALID_CATEGORIES)}"
            )
        return v


class WorkflowStepIn(BaseModel):
    title: str
    description: str | None = None
    owner_role: str = "member"
    estimated_hours: Decimal = Decimal("0")
    required: bool = True

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        if len(v) > 255:
            raise ValueError("title cannot exceed 255 characters")
        return v

    @field_validator("owner_role")
    @classmethod
    def validate_owner_role(cls, v: str) -> str:
        if v not in _VALID_OWNER_ROLES:
            raise ValueError(
                f"owner_role must be one of {sorted(_VALID_OWNER_ROLES)}"
            )
        return v

    @field_validator("estimated_hours")
    @classmethod
    def validate_estimated_hours(cls, v: Decimal) -> Decimal:
        if v < Decimal("0"):
            raise ValueError("estimated_hours must be >= 0")
        return v


class WorkflowStepUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner_role: str | None = None
    estimated_hours: Decimal | None = None
    required: bool | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        if len(v) > 255:
            raise ValueError("title cannot exceed 255 characters")
        return v

    @field_validator("owner_role")
    @classmethod
    def validate_owner_role(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _VALID_OWNER_ROLES:
            raise ValueError(
                f"owner_role must be one of {sorted(_VALID_OWNER_ROLES)}"
            )
        return v

    @field_validator("estimated_hours")
    @classmethod
    def validate_estimated_hours(cls, v: Decimal | None) -> Decimal | None:
        if v is None:
            return v
        if v < Decimal("0"):
            raise ValueError("estimated_hours must be >= 0")
        return v


class ReorderStepsIn(BaseModel):
    """Full ordered list of step IDs for the template."""
    step_ids: list[uuid.UUID]


# ── Output schemas ────────────────────────────────────────────────────────────

class WorkflowStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_template_id: uuid.UUID
    step_order: int
    title: str
    description: str | None
    owner_role: str
    estimated_hours: Decimal
    required: bool
    created_at: datetime


class WorkflowTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    category: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    steps: list[WorkflowStepOut] = []


class WorkflowTemplateListPage(BaseModel):
    items: list[WorkflowTemplateOut]
    next_cursor: str | None
    has_more: bool


# ── Execution Engine schemas — Sprint 34 ─────────────────────────────────────

_VALID_RUN_STATUSES: frozenset[str] = frozenset({
    "pending", "active", "completed", "cancelled"
})
_VALID_STEP_RUN_STATUSES: frozenset[str] = frozenset({
    "pending", "in_progress", "completed", "skipped", "blocked"
})


class WorkflowRunIn(BaseModel):
    workspace_id: uuid.UUID
    workflow_template_id: uuid.UUID
    title: str
    assigned_to: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        if len(v) > 255:
            raise ValueError("title cannot exceed 255 characters")
        return v


class CompleteStepIn(BaseModel):
    notes: str | None = None


class BlockStepIn(BaseModel):
    notes: str | None = None


class SkipStepIn(BaseModel):
    notes: str | None = None


# ── Run output schemas ─────────────────────────────────────────────────────────

class WorkflowRunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_run_id: uuid.UUID
    template_step_id: uuid.UUID | None
    title: str
    description: str | None
    owner_role: str
    required: bool
    step_order: int
    status: str
    completed_by: uuid.UUID | None
    completed_at: datetime | None
    notes: str | None


class WorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_template_id: uuid.UUID | None
    title: str
    status: str
    started_by: uuid.UUID
    assigned_to: uuid.UUID | None
    started_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    run_steps: list[WorkflowRunStepOut] = []


class WorkflowRunListPage(BaseModel):
    items: list[WorkflowRunOut]
    next_cursor: str | None
    has_more: bool
