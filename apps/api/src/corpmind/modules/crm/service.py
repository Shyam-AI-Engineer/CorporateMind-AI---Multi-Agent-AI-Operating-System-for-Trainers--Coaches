"""CRM service."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class CRMService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    # TODO(Phase 1): implement create_lead(), advance_stage(), list_pipeline()
