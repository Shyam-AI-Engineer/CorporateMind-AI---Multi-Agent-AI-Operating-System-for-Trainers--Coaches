"""Workflow Templates & Playbooks + Execution Engine domain events — Sprint 33/34."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowTemplateCreated:
    template_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    category: str
    created_by: uuid.UUID


@dataclass(frozen=True)
class WorkflowTemplateUpdated:
    template_id: uuid.UUID
    workspace_id: uuid.UUID
    changed_fields: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowTemplateDeleted:
    template_id: uuid.UUID
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class WorkflowTemplateDuplicated:
    source_template_id: uuid.UUID
    new_template_id: uuid.UUID
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class WorkflowStepAdded:
    step_id: uuid.UUID
    template_id: uuid.UUID
    step_order: int


@dataclass(frozen=True)
class WorkflowStepUpdated:
    step_id: uuid.UUID
    template_id: uuid.UUID
    changed_fields: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowStepDeleted:
    step_id: uuid.UUID
    template_id: uuid.UUID


@dataclass(frozen=True)
class WorkflowStepsReordered:
    template_id: uuid.UUID
    step_count: int


# ── Execution Engine events — Sprint 34 ──────────────────────────────────────

from datetime import datetime  # noqa: E402 — kept local to avoid top-level churn


@dataclass(frozen=True)
class WorkflowRunStarted:
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    template_id: uuid.UUID | None
    title: str
    started_by: uuid.UUID
    assigned_to: uuid.UUID | None


@dataclass(frozen=True)
class WorkflowRunCancelled:
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    cancelled_by: uuid.UUID


@dataclass(frozen=True)
class WorkflowRunCompleted:
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    completed_at: datetime


@dataclass(frozen=True)
class WorkflowRunStepCompleted:
    step_id: uuid.UUID
    run_id: uuid.UUID
    completed_by: uuid.UUID


@dataclass(frozen=True)
class WorkflowRunStepReopened:
    step_id: uuid.UUID
    run_id: uuid.UUID
    reopened_by: uuid.UUID


@dataclass(frozen=True)
class WorkflowRunStepSkipped:
    step_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class WorkflowRunStepBlocked:
    step_id: uuid.UUID
    run_id: uuid.UUID


@dataclass(frozen=True)
class WorkflowRunStepResumed:
    step_id: uuid.UUID
    run_id: uuid.UUID
