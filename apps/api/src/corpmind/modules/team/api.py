"""Team module API — Sprint 30.

Endpoints:
  GET    /team/members           — list active workspace members
  POST   /team/invite            — invite a user (owner/admin only)
  POST   /team/accept            — accept an invitation
  PATCH  /team/{member_id}/role  — change a member's role (owner/admin only)
  DELETE /team/{member_id}       — remove a member (owner/admin only)
  GET    /team/activity          — cursor-paginated activity feed
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.team.schemas import (
    ActivityFeedPage,
    MemberAcceptIn,
    MemberInviteIn,
    MemberListOut,
    MemberRoleUpdate,
    WorkspaceMemberOut,
)
from corpmind.modules.team.service import (
    ActivityFeedService,
    PermissionDeniedError,
    WorkspaceMemberService,
)

router = APIRouter()


def _handle_permission(exc: PermissionDeniedError) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def _handle_not_found(exc: Exception) -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/members", response_model=MemberListOut)
async def list_members(
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> MemberListOut:
    """Return all active (non-removed) members of a workspace."""
    return await WorkspaceMemberService(session).list_members(workspace_id)


@router.post("/invite", response_model=WorkspaceMemberOut, status_code=status.HTTP_201_CREATED)
async def invite_member(
    data: MemberInviteIn,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMemberOut:
    """Invite a user to the workspace. Requires owner or admin role."""
    try:
        return await WorkspaceMemberService(session).invite(data)
    except PermissionDeniedError as exc:
        _handle_permission(exc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/accept", response_model=WorkspaceMemberOut)
async def accept_invitation(
    data: MemberAcceptIn,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMemberOut:
    """Accept a pending workspace invitation."""
    try:
        return await WorkspaceMemberService(session).accept_invitation(
            data.member_id, data.workspace_id
        )
    except PermissionDeniedError as exc:
        _handle_permission(exc)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/{member_id}/role", response_model=WorkspaceMemberOut)
async def change_member_role(
    member_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    data: MemberRoleUpdate = ...,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMemberOut:
    """Change a workspace member's role. Requires owner or admin role."""
    try:
        return await WorkspaceMemberService(session).change_role(member_id, workspace_id, data)
    except PermissionDeniedError as exc:
        _handle_permission(exc)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove (soft-delete) a workspace member. Requires owner or admin role."""
    try:
        await WorkspaceMemberService(session).remove(member_id, workspace_id)
    except PermissionDeniedError as exc:
        _handle_permission(exc)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/activity", response_model=ActivityFeedPage)
async def list_activity(
    workspace_id: uuid.UUID = Query(...),
    cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    session: AsyncSession = Depends(get_session),
) -> ActivityFeedPage:
    """Return a cursor-paginated activity feed for the workspace, newest-first."""
    return await ActivityFeedService(session).list_page(workspace_id, cursor, limit)
