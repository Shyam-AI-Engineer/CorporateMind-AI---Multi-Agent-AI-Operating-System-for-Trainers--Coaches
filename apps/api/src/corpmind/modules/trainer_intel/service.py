"""Trainer intelligence service."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class TrainerIntelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # TODO(Phase 1): implement extract_from_upload(), lock_profile()
    # Delegates to TrainerProfileAgent via Celery.
