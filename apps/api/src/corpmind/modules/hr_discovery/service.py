"""HR discovery service."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class HRDiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # TODO(Phase 1): implement discover(), enrich_contact()
    # Delegates to HRDiscoveryAgent via Celery.
