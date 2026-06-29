"""Approval workflow API — Sprint 31.

Endpoints:
  GET  /approvals                 — list workspace approval requests (cursor-paginated)
  GET  /approvals/my-reviews      — list requests assigned to the current user
  POST /approvals                 — create a new approval request
  GET  /approvals/{id}            — get a single approval request
  PATCH /approvals/{id}/assign    — assign a reviewer
  POST /approvals/{id}/approve    — approve the request
  POST /approvals/{id}/reject     — reject the request
  POST /approvals/{id}/cancel     — cancel the request
  GET  /approvals/{id}/timeline   — ordered audit trail for the request

NOTE: /approvals/my-reviews is registered before /{id} routes so the static
segment wins over the parameterized one.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.approvals.schemas import (
    ApprovalAssignIn,
    ApprovalDecisionIn,
    ApprovalListPage,
    ApprovalRequestIn,
    ApprovalRequestOut,
    ApprovalTimelineEventOut,
)
from corpmind.modules.approvals.service import (
    ApprovalService,
    ApprovalTimelineService,
    InvalidStateError,
    PermissionDeniedError,
)

router = APIRouter()


def _raise_permission(exc: PermissionDeniedError) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def _raise_not_found(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _raise_conflict(exc: InvalidStateError) -> None:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/my-reviews", response_model=ApprovalListPage)
async def list_my_reviews(
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    session: AsyncSession = Depends(get_session),
) -> ApprovalListPage:
    """Return approval requests assigned to the current user, newest-first."""
    return await ApprovalService(session).list_my_reviews(workspace_id, cursor, limit)


@router.get("", response_model=ApprovalListPage)
async def list_approvals(
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    assigned_reviewer: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> ApprovalListPage:
    """Return cursor-paginated workspace approval requests, newest-first."""
    return await ApprovalService(session).list_requests(
        workspace_id, cursor, limit, status_filter, priority, assigned_reviewer
    )


@router.post("", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
async def create_approval(
    data: ApprovalRequestIn,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestOut:
    """Create a new approval request."""
    return await ApprovalService(session).create_request(data)


@router.get("/{approval_id}", response_model=ApprovalRequestOut)
async def get_approval(
    approval_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestOut:
    """Return a single approval request by ID."""
    try:
        return await ApprovalService(session).get_detail(approval_id, workspace_id)
    except Exception as exc:
        _raise_not_found(exc)


@router.patch("/{approval_id}/assign", response_model=ApprovalRequestOut)
async def assign_reviewer(
    approval_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    data: ApprovalAssignIn = ...,
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestOut:
    """Assign a reviewer to the approval request."""
    try:
        return await ApprovalService(session).assign_reviewer(approval_id, workspace_id, data)
    except PermissionDeniedError as exc:
        _raise_permission(exc)
    except InvalidStateError as exc:
        _raise_conflict(exc)
    except Exception as exc:
        _raise_not_found(exc)


@router.post("/{approval_id}/approve", response_model=ApprovalRequestOut)
async def approve_request(
    approval_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    data: ApprovalDecisionIn = ApprovalDecisionIn(),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestOut:
    """Approve the request (assigned reviewer or org admin)."""
    try:
        return await ApprovalService(session).approve(approval_id, workspace_id, data)
    except PermissionDeniedError as exc:
        _raise_permission(exc)
    except InvalidStateError as exc:
        _raise_conflict(exc)
    except Exception as exc:
        _raise_not_found(exc)


@router.post("/{approval_id}/reject", response_model=ApprovalRequestOut)
async def reject_request(
    approval_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    data: ApprovalDecisionIn = ApprovalDecisionIn(),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestOut:
    """Reject the request (assigned reviewer or org admin)."""
    try:
        return await ApprovalService(session).reject(approval_id, workspace_id, data)
    except PermissionDeniedError as exc:
        _raise_permission(exc)
    except InvalidStateError as exc:
        _raise_conflict(exc)
    except Exception as exc:
        _raise_not_found(exc)


@router.post("/{approval_id}/cancel", response_model=ApprovalRequestOut)
async def cancel_request(
    approval_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestOut:
    """Cancel the request (requester or org admin)."""
    try:
        return await ApprovalService(session).cancel(approval_id, workspace_id)
    except PermissionDeniedError as exc:
        _raise_permission(exc)
    except InvalidStateError as exc:
        _raise_conflict(exc)
    except Exception as exc:
        _raise_not_found(exc)


@router.get("/{approval_id}/timeline", response_model=list[ApprovalTimelineEventOut])
async def list_timeline(
    approval_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalTimelineEventOut]:
    """Return the ordered audit trail for an approval request."""
    try:
        return await ApprovalTimelineService(session).list_timeline(
            approval_id, workspace_id
        )
    except Exception as exc:
        _raise_not_found(exc)
