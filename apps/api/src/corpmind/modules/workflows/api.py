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
    BlockStepIn,
    CompleteStepIn,
    ReorderStepsIn,
    SkipStepIn,
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
)
from corpmind.modules.workflows.service import (
    PermissionDeniedError,
    SkipRequiredStepError,
    StepOrderConflictError,
    StepStateError,
    WorkflowExecutionService,
    WorkflowRunImmutableError,
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


@run_router.get("/{run_id}", response_model=WorkflowRunOut)
async def get_run(
    run_id: uuid.UUID,
    svc: WorkflowExecutionService = Depends(_exec_svc),
) -> WorkflowRunOut:
    try:
        return await svc.get_run(run_id)
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
