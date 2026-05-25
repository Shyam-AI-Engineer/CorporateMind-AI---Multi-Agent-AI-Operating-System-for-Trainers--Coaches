"""Trainer intelligence repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.trainer_intel.models import TrainerProfile


class TrainerProfileRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_for_workspace(self, workspace_id: uuid.UUID) -> TrainerProfile | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(TrainerProfile).where(
                TrainerProfile.tenant_id == ctx.org_id,
                TrainerProfile.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, profile: TrainerProfile) -> TrainerProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile
