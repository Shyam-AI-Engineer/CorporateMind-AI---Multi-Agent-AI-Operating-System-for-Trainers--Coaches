"""Approval workflow models — Sprint 31."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from corpmind.core.database import TenantBase


class ApprovalRequest(TenantBase):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # entity_type: task | recommendation | campaign | proposal
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    # String user-ids so there's no hard FK to users table (matches operations pattern)
    requested_by: Mapped[str] = mapped_column(String(256), nullable=False)
    assigned_reviewer: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    # priority: low | medium | high | urgent
    priority: Mapped[str] = mapped_column(
        String(32), nullable=False, default="medium", server_default="medium"
    )
    # status: pending | in_review | approved | rejected | cancelled
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    # decision: approve | reject | none
    decision: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none", server_default="none"
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApprovalTimelineEvent(TenantBase):
    __tablename__ = "approval_timeline"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    # event_type: request_created | reviewer_assigned | review_started |
    #              approved | rejected | cancelled
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
