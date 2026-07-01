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
    started_at: datetime | None
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
    # Sprint 35: entity context (nullable — attachment is optional)
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    entity_title: str | None = None
    run_steps: list[WorkflowRunStepOut] = []


class WorkflowRunListPage(BaseModel):
    items: list[WorkflowRunOut]
    next_cursor: str | None
    has_more: bool


# ── Entity Integration schemas — Sprint 35 ────────────────────────────────────

_VALID_ENTITY_TYPES: frozenset[str] = frozenset({
    "lead", "proposal", "campaign", "customer", "training", "other"
})


class AttachEntityIn(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    entity_title: str

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in _VALID_ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of {sorted(_VALID_ENTITY_TYPES)}"
            )
        return v

    @field_validator("entity_title")
    @classmethod
    def validate_entity_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("entity_title cannot be empty")
        if len(v) > 255:
            raise ValueError("entity_title cannot exceed 255 characters")
        return v


class EntityRunListPage(BaseModel):
    items: list[WorkflowRunOut]
    next_cursor: str | None
    has_more: bool


# ── Workflow Analytics schemas — Sprint 36 ────────────────────────────────────

_VALID_TREND_PERIODS: frozenset[int] = frozenset({7, 30, 90})


class AnalyticsSummaryOut(BaseModel):
    total_runs: int
    active_runs: int
    completed_runs: int
    cancelled_runs: int
    completion_rate: float
    average_completion_days: float
    average_step_completion_days: float
    average_required_steps: float
    average_optional_steps: float
    data_integrity_warning: bool


class TemplateAnalyticsItem(BaseModel):
    template_id: str | None
    template_name: str
    runs: int
    completed: int
    cancelled: int
    completion_rate: float
    average_completion_days: float
    average_steps: float
    average_required_steps: float
    average_optional_steps: float


class TemplateAnalyticsOut(BaseModel):
    items: list[TemplateAnalyticsItem]


class BottleneckItem(BaseModel):
    step_name: str
    template_name: str
    times_executed: int
    average_days: float
    completion_rate: float
    blocked_count: int
    skip_count: int


class BottleneckAnalyticsOut(BaseModel):
    items: list[BottleneckItem]


class TrendBucket(BaseModel):
    date: str
    runs_started: int
    runs_completed: int
    runs_cancelled: int
    completion_rate: float


class TrendAnalyticsOut(BaseModel):
    period: int
    buckets: list[TrendBucket]


class WorkloadItem(BaseModel):
    owner: str
    pending_steps: int
    completed_steps: int
    blocked_steps: int
    completion_rate: float
    average_completion_days: float


class WorkloadAnalyticsOut(BaseModel):
    items: list[WorkloadItem]


# ── Workflow SLA schemas — Sprint 37 ─────────────────────────────────────────

_WORKFLOW_SLA_DAYS: int = 30
_STEP_SLA_DAYS: int = 7
_VALID_SLA_PERIODS: frozenset[int] = frozenset({7, 30, 90})


class SLASummaryOut(BaseModel):
    active_runs: int
    overdue_runs: int
    sla_compliance_rate: float
    average_days_open: float
    average_days_overdue: float
    critical_overdue: int
    warning_overdue: int
    healthy_runs: int
    data_integrity_warning: bool


class SLAOverdueItem(BaseModel):
    run_id: str
    title: str
    template_name: str | None
    entity_type: str | None
    entity_title: str | None
    started_at: str
    days_open: float
    days_overdue: float
    current_step: str | None
    owner_role: str | None


class SLAOverdueOut(BaseModel):
    items: list[SLAOverdueItem]


class SLATemplateItem(BaseModel):
    template_id: str | None
    template_name: str
    runs: int
    overdue: int
    compliance_rate: float
    average_duration_days: float
    average_days_overdue: float


class SLATemplateOut(BaseModel):
    items: list[SLATemplateItem]


class SLAOwnerItem(BaseModel):
    owner_role: str
    assigned_steps: int
    completed_steps: int
    overdue_steps: int
    compliance_rate: float
    average_completion_days: float


class SLAOwnerOut(BaseModel):
    items: list[SLAOwnerItem]


class SLATrendBucket(BaseModel):
    date: str
    healthy: int
    warning: int
    critical: int
    completed: int


class SLATrendOut(BaseModel):
    period: int
    buckets: list[SLATrendBucket]


# ── Workflow Effectiveness schemas — Sprint 38 ─────────────────────────────────


class EffectivenessSummaryOut(BaseModel):
    total_completed: int
    average_completion_days: float
    average_step_completion_days: float
    entity_coverage: float
    fast_completion_rate: float
    slow_completion_rate: float
    overall_effectiveness_score: float
    data_integrity_warning: bool


class EffectivenessTemplateItem(BaseModel):
    template_id: str | None
    template_name: str
    runs: int
    completed: int
    completion_rate: float
    average_duration: float
    effectiveness_score: float


class EffectivenessTemplateOut(BaseModel):
    items: list[EffectivenessTemplateItem]


class EffectivenessEntityItem(BaseModel):
    entity_type: str
    workflow_count: int
    completion_rate: float
    average_duration: float
    effectiveness_score: float


class EffectivenessEntityOut(BaseModel):
    items: list[EffectivenessEntityItem]


class DurationBucketItem(BaseModel):
    label: str
    completed: int
    completion_rate: float
    average_steps: float
    effectiveness_score: float


class DurationImpactOut(BaseModel):
    buckets: list[DurationBucketItem]


class CompletionImpactItem(BaseModel):
    status: str
    count: int
    average_duration: float
    effectiveness_score: float


class CompletionImpactOut(BaseModel):
    items: list[CompletionImpactItem]


# ── Workflow Observability schemas — Sprint 39 ─────────────────────────────────


class BottleneckObsItem(BaseModel):
    template_name: str
    slowest_step: str
    average_days: float
    max_days: float
    runs_affected: int
    bottleneck_score: float


class BottleneckObsOut(BaseModel):
    items: list[BottleneckObsItem]


class StepAnalysisItem(BaseModel):
    step_name: str
    completed_count: int
    average_completion_days: float
    median_completion_days: float
    blocked_count: int
    skip_rate: float
    completion_rate: float


class StepAnalysisOut(BaseModel):
    items: list[StepAnalysisItem]


class OwnerCapacityItem(BaseModel):
    owner_role: str
    assigned_steps: int
    completed_steps: int
    blocked_steps: int
    average_completion_days: float
    capacity_score: float


class OwnerCapacityOut(BaseModel):
    items: list[OwnerCapacityItem]


class TemplateCapacityItem(BaseModel):
    template_name: str
    active_runs: int
    completed_runs: int
    average_parallel_runs: float
    average_completion_days: float
    capacity_rating: str


class TemplateCapacityOut(BaseModel):
    items: list[TemplateCapacityItem]


class FlowHealthOut(BaseModel):
    healthy_flows: int
    warning_flows: int
    critical_flows: int
    average_step_completion_days: float
    average_run_completion_days: float
    flow_health_score: float
    data_integrity_warning: bool
