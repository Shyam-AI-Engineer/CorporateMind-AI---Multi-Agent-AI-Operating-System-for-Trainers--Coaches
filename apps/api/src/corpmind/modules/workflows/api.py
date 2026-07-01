"""Workflow Templates & Playbooks + Execution Engine API — Sprint 33/34.

Endpoints:
  GET    /workflow-templates                    — list templates (paginated)
  POST   /workflow-templates                    — create template
  GET    /workflow-templates/{id}               — get template detail + steps
  PATCH  /workflow-templates/{id}               — update template metadata
  DELETE /workflow-templates/{id}               — delete template + cascade steps
  POST   /workflow-templates/{id}/duplicate     — duplicate template
  POST   /workflow-templates/{id}/steps         — add step to template
  POST   /workflow-templates/{id}/reorder       — reorder all steps
  PATCH  /workflow-steps/{id}                   — update a step
  DELETE /workflow-steps/{id}                   — delete a step
"""

from __future__ import annotations

import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.core.exceptions import NotFoundError
from corpmind.modules.workflows.schemas import (
    AnalyticsSummaryOut,
    AttachEntityIn,
    BlockStepIn,
    BottleneckAnalyticsOut,
    CompleteStepIn,
    CompletionImpactOut,
    DurationImpactOut,
    EffectivenessEntityOut,
    EffectivenessSummaryOut,
    EffectivenessTemplateOut,
    EntityRunListPage,
    ReorderStepsIn,
    SLAOverdueOut,
    SLAOwnerOut,
    SLASummaryOut,
    SLATemplateOut,
    SLATrendOut,
    SkipStepIn,
    TemplateAnalyticsOut,
    TrendAnalyticsOut,
    WorkflowRunIn,
    WorkflowRunListPage,
    WorkflowRunOut,
    WorkflowRunStepOut,
    WorkflowStepIn,
    WorkflowStepOut,
    WorkflowStepUpdate,
    WorkflowTemplateIn,
    WorkflowTemplateListPage,
    WorkflowTemplateOut,
    WorkflowTemplateUpdate,
    WorkloadAnalyticsOut,
    BottleneckObsOut,
    FlowHealthOut,
    OwnerCapacityOut,
    StepAnalysisOut,
    TemplateCapacityOut,
)
from corpmind.modules.workflows.service import (
    DuplicateActiveEntityRunError,
    PermissionDeniedError,
    SkipRequiredStepError,
    StepOrderConflictError,
    StepStateError,
    WorkflowAnalyticsService,
    WorkflowEffectivenessService,
    WorkflowExecutionService,
    WorkflowObservabilityService,
    WorkflowRunImmutableError,
    WorkflowSLAService,
    WorkflowService,
)

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> WorkflowService:
    return WorkflowService(session)


def _not_found(exc: Exception) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _forbidden(exc: Exception) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def _conflict(exc: Exception) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# ── Template endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=WorkflowTemplateListPage)
async def list_templates(
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    category: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    svc: WorkflowService = Depends(_svc),
) -> WorkflowTemplateListPage:
    return await svc.list_templates(workspace_id, cursor, limit, category, is_active)


@router.post("", response_model=WorkflowTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: WorkflowTemplateIn,
    svc: WorkflowService = Depends(_svc),
) -> WorkflowTemplateOut:
    try:
        return await svc.create_template(data)
    except PermissionDeniedError as exc:
        _forbidden(exc)


@router.get("/{template_id}", response_model=WorkflowTemplateOut)
async def get_template(
    template_id: uuid.UUID,
    svc: WorkflowService = Depends(_svc),
) -> WorkflowTemplateOut:
    try:
        return await svc.get_template(template_id)
    except NotFoundError as exc:
        _not_found(exc)


@router.patch("/{template_id}", response_model=WorkflowTemplateOut)
async def update_template(
    template_id: uuid.UUID,
    data: WorkflowTemplateUpdate,
    svc: WorkflowService = Depends(_svc),
) -> WorkflowTemplateOut:
    try:
        return await svc.update_template(template_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    svc: WorkflowService = Depends(_svc),
) -> None:
    try:
        await svc.delete_template(template_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@router.post("/{template_id}/duplicate", response_model=WorkflowTemplateOut, status_code=status.HTTP_201_CREATED)
async def duplicate_template(
    template_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowService = Depends(_svc),
) -> WorkflowTemplateOut:
    try:
        return await svc.duplicate_template(template_id, workspace_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@router.post("/{template_id}/steps", response_model=WorkflowStepOut, status_code=status.HTTP_201_CREATED)
async def add_step(
    template_id: uuid.UUID,
    data: WorkflowStepIn,
    svc: WorkflowService = Depends(_svc),
) -> WorkflowStepOut:
    try:
        return await svc.add_step(template_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@router.post("/{template_id}/reorder", response_model=WorkflowTemplateOut)
async def reorder_steps(
    template_id: uuid.UUID,
    data: ReorderStepsIn,
    svc: WorkflowService = Depends(_svc),
) -> WorkflowTemplateOut:
    try:
        return await svc.reorder_steps(template_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except StepOrderConflictError as exc:
        _conflict(exc)


# ── Step endpoints (no template prefix) ──────────────────────────────────────

steps_router = APIRouter()


@steps_router.patch("/{step_id}", response_model=WorkflowStepOut)
async def update_step(
    step_id: uuid.UUID,
    data: WorkflowStepUpdate,
    svc: WorkflowService = Depends(_svc),
) -> WorkflowStepOut:
    try:
        return await svc.update_step(step_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@steps_router.delete("/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(
    step_id: uuid.UUID,
    svc: WorkflowService = Depends(_svc),
) -> None:
    try:
        await svc.delete_step(step_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


# ── Execution Engine routers — Sprint 34 ─────────────────────────────────────

def _exec_svc(session: AsyncSession = Depends(get_session)) -> WorkflowExecutionService:
    return WorkflowExecutionService(session)


def _immutable(exc: Exception) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def _unprocessable(exc: Exception) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
    )


run_router = APIRouter()


@run_router.get("", response_model=WorkflowRunListPage)
async def list_runs(
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_filter: str | None = Query(default=None),
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunListPage:
    return await svc.list_runs(workspace_id, cursor, limit, status_filter)


@run_router.post("", response_model=WorkflowRunOut, status_code=status.HTTP_201_CREATED)
async def start_run(
    data: WorkflowRunIn,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut:
    try:
        return await svc.start_run(data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@run_router.get("/entity/{entity_type}/{entity_id}/active", response_model=WorkflowRunOut | None)
async def get_active_entity_run(
    entity_type: str,
    entity_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut | None:
    return await svc.find_active_run(workspace_id, entity_type, entity_id)


@run_router.get("/entity/{entity_type}/{entity_id}", response_model=EntityRunListPage)
async def list_entity_runs(
    entity_type: str,
    entity_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> EntityRunListPage:
    return await svc.list_entity_runs(workspace_id, entity_type, entity_id, cursor, limit)


@run_router.get("/{run_id}", response_model=WorkflowRunOut)
async def get_run(
    run_id: uuid.UUID,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut:
    try:
        return await svc.get_run(run_id)
    except NotFoundError as exc:
        _not_found(exc)


@run_router.post("/{run_id}/attach", response_model=WorkflowRunOut)
async def attach_entity(
    run_id: uuid.UUID,
    data: AttachEntityIn,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut:
    try:
        return await svc.attach_entity(run_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except DuplicateActiveEntityRunError as exc:
        _conflict(exc)


@run_router.post("/{run_id}/detach", response_model=WorkflowRunOut)
async def detach_entity(
    run_id: uuid.UUID,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut:
    try:
        return await svc.detach_entity(run_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)


@run_router.post("/{run_id}/cancel", response_model=WorkflowRunOut)
async def cancel_run(
    run_id: uuid.UUID,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut:
    try:
        return await svc.cancel_run(run_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except WorkflowRunImmutableError as exc:
        _immutable(exc)


# ── Run-step action router ────────────────────────────────────────────────────

run_steps_router = APIRouter()


@run_steps_router.post("/{step_id}/complete", response_model=WorkflowRunStepOut)
async def complete_step(
    step_id: uuid.UUID,
    data: CompleteStepIn,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunStepOut:
    try:
        return await svc.complete_step(step_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except WorkflowRunImmutableError as exc:
        _immutable(exc)


@run_steps_router.post("/{step_id}/reopen", response_model=WorkflowRunStepOut)
async def reopen_step(
    step_id: uuid.UUID,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunStepOut:
    try:
        return await svc.reopen_step(step_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except WorkflowRunImmutableError as exc:
        _immutable(exc)


@run_steps_router.post("/{step_id}/skip", response_model=WorkflowRunStepOut)
async def skip_step(
    step_id: uuid.UUID,
    data: SkipStepIn,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunStepOut:
    try:
        return await svc.skip_step(step_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except WorkflowRunImmutableError as exc:
        _immutable(exc)
    except SkipRequiredStepError as exc:
        _unprocessable(exc)


@run_steps_router.post("/{step_id}/block", response_model=WorkflowRunStepOut)
async def block_step(
    step_id: uuid.UUID,
    data: BlockStepIn,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunStepOut:
    try:
        return await svc.block_step(step_id, data)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except WorkflowRunImmutableError as exc:
        _immutable(exc)


@run_steps_router.post("/{step_id}/resume", response_model=WorkflowRunStepOut)
async def resume_step(
    step_id: uuid.UUID,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunStepOut:
    try:
        return await svc.resume_step(step_id)
    except PermissionDeniedError as exc:
        _forbidden(exc)
    except NotFoundError as exc:
        _not_found(exc)
    except WorkflowRunImmutableError as exc:
        _immutable(exc)
    except StepStateError as exc:
        _unprocessable(exc)


# ── Workflow Analytics endpoints — Sprint 36 ──────────────────────────────────

analytics_router = APIRouter()

_VALID_PERIODS = frozenset({7, 30, 90})


def _analytics_svc(session: AsyncSession = Depends(get_session)) -> WorkflowAnalyticsService:
    return WorkflowAnalyticsService(session)


@analytics_router.get("/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowAnalyticsService = Depends(_analytics_svc),
) -> AnalyticsSummaryOut:
    return await svc.get_summary(workspace_id)


@analytics_router.get("/templates", response_model=TemplateAnalyticsOut)
async def get_analytics_templates(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowAnalyticsService = Depends(_analytics_svc),
) -> TemplateAnalyticsOut:
    return await svc.get_template_analytics(workspace_id)


@analytics_router.get("/bottlenecks", response_model=BottleneckAnalyticsOut)
async def get_analytics_bottlenecks(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowAnalyticsService = Depends(_analytics_svc),
) -> BottleneckAnalyticsOut:
    return await svc.get_bottlenecks(workspace_id)


@analytics_router.get("/trends", response_model=TrendAnalyticsOut)
async def get_analytics_trends(
    workspace_id: uuid.UUID = Query(...),
    period: Annotated[int, Query(ge=1, le=365)] = 30,
    svc: WorkflowAnalyticsService = Depends(_analytics_svc),
) -> TrendAnalyticsOut:
    if period not in _VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"period must be one of {sorted(_VALID_PERIODS)}",
        )
    return await svc.get_trends(workspace_id, period)


@analytics_router.get("/workload", response_model=WorkloadAnalyticsOut)
async def get_analytics_workload(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowAnalyticsService = Depends(_analytics_svc),
) -> WorkloadAnalyticsOut:
    return await svc.get_workload(workspace_id)


# ── Workflow SLA endpoints — Sprint 37 ───────────────────────────────────────

sla_router = APIRouter()

_VALID_SLA_PERIODS = frozenset({7, 30, 90})


def _sla_svc(session: AsyncSession = Depends(get_session)) -> WorkflowSLAService:
    return WorkflowSLAService(session)


@sla_router.get("/summary", response_model=SLASummaryOut)
async def get_sla_summary(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowSLAService = Depends(_sla_svc),
) -> SLASummaryOut:
    return await svc.get_summary(workspace_id)


@sla_router.get("/overdue", response_model=SLAOverdueOut)
async def get_sla_overdue(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowSLAService = Depends(_sla_svc),
) -> SLAOverdueOut:
    return await svc.get_overdue(workspace_id)


@sla_router.get("/by-template", response_model=SLATemplateOut)
async def get_sla_by_template(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowSLAService = Depends(_sla_svc),
) -> SLATemplateOut:
    return await svc.get_template_sla(workspace_id)


@sla_router.get("/by-owner", response_model=SLAOwnerOut)
async def get_sla_by_owner(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowSLAService = Depends(_sla_svc),
) -> SLAOwnerOut:
    return await svc.get_owner_sla(workspace_id)


@sla_router.get("/trend", response_model=SLATrendOut)
async def get_sla_trend(
    workspace_id: uuid.UUID = Query(...),
    period: Annotated[int, Query(ge=1, le=365)] = 30,
    svc: WorkflowSLAService = Depends(_sla_svc),
) -> SLATrendOut:
    if period not in _VALID_SLA_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"period must be one of {sorted(_VALID_SLA_PERIODS)}",
        )
    return await svc.get_trend(workspace_id, period)


# ── Workflow Effectiveness endpoints — Sprint 38 ──────────────────────────────

effectiveness_router = APIRouter()


def _eff_svc(
    session: AsyncSession = Depends(get_session),
) -> WorkflowEffectivenessService:
    return WorkflowEffectivenessService(session)


@effectiveness_router.get("/summary", response_model=EffectivenessSummaryOut)
async def get_effectiveness_summary(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowEffectivenessService = Depends(_eff_svc),
) -> EffectivenessSummaryOut:
    return await svc.get_summary(workspace_id)


@effectiveness_router.get("/templates", response_model=EffectivenessTemplateOut)
async def get_effectiveness_templates(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowEffectivenessService = Depends(_eff_svc),
) -> EffectivenessTemplateOut:
    return await svc.get_template_effectiveness(workspace_id)


@effectiveness_router.get("/entity-types", response_model=EffectivenessEntityOut)
async def get_effectiveness_entity_types(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowEffectivenessService = Depends(_eff_svc),
) -> EffectivenessEntityOut:
    return await svc.get_entity_type_effectiveness(workspace_id)


@effectiveness_router.get("/duration-impact", response_model=DurationImpactOut)
async def get_effectiveness_duration_impact(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowEffectivenessService = Depends(_eff_svc),
) -> DurationImpactOut:
    return await svc.get_duration_impact(workspace_id)


@effectiveness_router.get("/completion-impact", response_model=CompletionImpactOut)
async def get_effectiveness_completion_impact(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowEffectivenessService = Depends(_eff_svc),
) -> CompletionImpactOut:
    return await svc.get_completion_impact(workspace_id)


# ── Workflow Observability endpoints — Sprint 39 ──────────────────────────────

observability_router = APIRouter()


def _obs_svc(
    session: AsyncSession = Depends(get_session),
) -> WorkflowObservabilityService:
    return WorkflowObservabilityService(session)


@observability_router.get("/bottlenecks", response_model=BottleneckObsOut)
async def get_obs_bottlenecks(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowObservabilityService = Depends(_obs_svc),
) -> BottleneckObsOut:
    return await svc.get_bottlenecks(workspace_id)


@observability_router.get("/step-analysis", response_model=StepAnalysisOut)
async def get_obs_step_analysis(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowObservabilityService = Depends(_obs_svc),
) -> StepAnalysisOut:
    return await svc.get_step_analysis(workspace_id)


@observability_router.get("/owner-capacity", response_model=OwnerCapacityOut)
async def get_obs_owner_capacity(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowObservabilityService = Depends(_obs_svc),
) -> OwnerCapacityOut:
    return await svc.get_owner_capacity(workspace_id)


@observability_router.get("/template-capacity", response_model=TemplateCapacityOut)
async def get_obs_template_capacity(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowObservabilityService = Depends(_obs_svc),
) -> TemplateCapacityOut:
    return await svc.get_template_capacity(workspace_id)


@observability_router.get("/flow-health", response_model=FlowHealthOut)
async def get_obs_flow_health(
    workspace_id: uuid.UUID = Query(...),
    svc: WorkflowObservabilityService = Depends(_obs_svc),
) -> FlowHealthOut:
    return await svc.get_flow_health(workspace_id)
