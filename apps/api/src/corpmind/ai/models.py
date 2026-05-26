"""ORM models for AI usage tracking."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class ModelRun(TenantBase):
    """One LLM call through the Euri gateway.

    Written by EuriClient._record_usage() after every call.
    Queryable per-tenant per-day for billing reconciliation and cost dashboards.
    """

    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prompt_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_inr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
