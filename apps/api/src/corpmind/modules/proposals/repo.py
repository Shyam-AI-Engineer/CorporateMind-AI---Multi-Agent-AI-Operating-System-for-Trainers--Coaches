"""Proposals repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.modules.proposals.models import Proposal


class ProposalRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, proposal: Proposal) -> Proposal:
        self._session.add(proposal)
        await self._session.flush()
        return proposal
