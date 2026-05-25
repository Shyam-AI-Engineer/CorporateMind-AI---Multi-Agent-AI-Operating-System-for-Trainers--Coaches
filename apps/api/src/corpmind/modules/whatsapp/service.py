"""WhatsApp service."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class WhatsAppService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    # TODO(Phase 1): implement check_24h_window(), submit_template(), send_message()
