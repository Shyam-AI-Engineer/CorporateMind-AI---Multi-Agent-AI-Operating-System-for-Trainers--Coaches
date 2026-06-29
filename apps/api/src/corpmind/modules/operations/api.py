"""Operations API — Sprint 29 Business Operations Center endpoints.

Sprint 30 additions:
  PATCH /tasks/{task_id}/assign — assign/unassign a task to a workspace user
  GET   /tasks/{task_id}/comments — list task comments (oldest-first)
  POST  /tasks/{task_id}/comments — add a comment (member+ role required)
  DELETE /comments/{comment_id}   — delete own comment
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.operations.schemas import (
    BusinessTaskIn,
    BusinessTaskOut,
    BusinessTaskUpdate,
    GroupedTasksOut,
    WorkloadOut,
)
from corpmind.modules.operations.service import BusinessOperationsService
from corpmind.modules.team.schemas import CommentIn, CommentOut, TaskAssignIn
from corpmind.modules.team.service import CommentService, PermissionDeniedError

router = APIRouter()


@router.get("/tasks", response_model=GroupedTasksOut)
async def list_tasks(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> GroupedTasksOut:
    """Return tasks grouped by status (backlog / in_progress / blocked / completed)."""
    return await BusinessOperationsService(session).list_tasks(workspace_id=workspace_id)


@router.post("/tasks", response_model=BusinessTaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: BusinessTaskIn,
    session: AsyncSession = Depends(get_session),
) -> BusinessTaskOut:
    """Create a new task. Creator is the authenticated user (from JWT)."""
    ctx = get_tenant_context()
    created_by = str(ctx.user_id)
    return await BusinessOperationsService(session).create_task(data, created_by=created_by)


@router.patch("/tasks/{task_id}", response_model=BusinessTaskOut)
async def update_task(
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    data: BusinessTaskUpdate,
    session: AsyncSession = Depends(get_session),
) -> BusinessTaskOut:
    """Update task status, assignee, or due_date."""
    return await BusinessOperationsService(session).update_task(
        task_id=task_id,
        workspace_id=workspace_id,
        data=data,
    )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Soft-delete a task (sets status = 'deleted')."""
    await BusinessOperationsService(session).delete_task(
        task_id=task_id,
        workspace_id=workspace_id,
    )


@router.get("/workload", response_model=WorkloadOut)
async def get_workload(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> WorkloadOut:
    """Return workload summary: totals, by_priority, by_assignee."""
    return await BusinessOperationsService(session).get_workload(workspace_id=workspace_id)


# ── Sprint 30 extensions ──────────────────────────────────────────────────────

@router.patch("/tasks/{task_id}/assign", response_model=BusinessTaskOut)
async def assign_task(
    task_id: uuid.UUID,
    data: TaskAssignIn,
    session: AsyncSession = Depends(get_session),
) -> BusinessTaskOut:
    """Assign or unassign a task to a workspace user.

    Members may only assign to themselves (assigned_user_id == ctx.user_id or None).
    Owners and admins may assign to anyone.
    """
    from corpmind.modules.team.repo import WorkspaceMemberRepo

    ctx = get_tenant_context()
    member_repo = WorkspaceMemberRepo(session)
    member = await member_repo.find_active_by_user(data.workspace_id, ctx.user_id)
    actor_role = member.role if member else "viewer"

    if actor_role == "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Viewers cannot assign tasks")
    if actor_role == "member" and data.assigned_user_id is not None and data.assigned_user_id != ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Members can only assign tasks to themselves",
        )

    return await BusinessOperationsService(session).assign_task(
        task_id=task_id,
        workspace_id=data.workspace_id,
        assigned_user_id=data.assigned_user_id,
    )


@router.get("/tasks/{task_id}/comments", response_model=list[CommentOut])
async def list_comments(
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CommentOut]:
    """Return all comments for a task, oldest-first."""
    return await CommentService(session).list(task_id=task_id, workspace_id=workspace_id)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    task_id: uuid.UUID,
    workspace_id: uuid.UUID,
    data: CommentIn,
    session: AsyncSession = Depends(get_session),
) -> CommentOut:
    """Add a comment to a task. Requires member or above role."""
    try:
        return await CommentService(session).create(
            task_id=task_id, workspace_id=workspace_id, data=data
        )
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a comment. Only the comment author may delete it."""
    try:
        await CommentService(session).delete_own(
            comment_id=comment_id, workspace_id=workspace_id
        )
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
