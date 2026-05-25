"""Social repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.social.models import SocialPost


class SocialPostRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, post: SocialPost) -> SocialPost:
        self._session.add(post)
        await self._session.flush()
        return post
