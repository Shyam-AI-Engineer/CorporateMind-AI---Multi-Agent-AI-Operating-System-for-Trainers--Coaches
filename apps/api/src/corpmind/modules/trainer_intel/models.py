"""Trainer intelligence module models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class TrainerProfile(TenantBase):
    """Extracted trainer intelligence from uploaded content."""

    __tablename__ = "trainer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    niche: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topics: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    tone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pricing_min_inr: Mapped[int | None] = mapped_column(nullable=True)
    pricing_max_inr: Mapped[int | None] = mapped_column(nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    usp: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_industries: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    languages: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    extraction_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
