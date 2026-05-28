"""Social module REST API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.social.schemas import (
    SocialPostCreate,
    SocialPostListOut,
    SocialPostOut,
)
from corpmind.modules.social.service import SocialService

router = APIRouter()


@router.post(
    "/posts",
    response_model=SocialPostOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a social post (draft or scheduled)",
)
async def create_post(
    req: SocialPostCreate,
    session: AsyncSession = Depends(get_session),
) -> SocialPostOut:
    return await SocialService(session).schedule_post(req)


@router.get(
    "/posts",
    response_model=SocialPostListOut,
    summary="List social posts for a workspace",
)
async def list_posts(
    workspace_id: uuid.UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> SocialPostListOut:
    return await SocialService(session).list_posts(
        workspace_id, limit=limit, offset=offset
    )


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a draft or scheduled post",
)
async def delete_post(
    post_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await SocialService(session).delete_post(post_id)
