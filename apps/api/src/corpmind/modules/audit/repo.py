"""Audit log repository — append-only.  No update or delete methods."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.audit.models import AuditLog
from corpmind.modules.audit.schemas import AuditStatisticsOut


# ── Cursor helpers ────────────────────────────────────────────────────────────

def _encode_audit_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    """Encode a (created_at, id) pair into a URL-safe base64 cursor token."""
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_audit_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor token produced by `_encode_audit_cursor`."""
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    ts_str, id_str = raw.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


# ── Repository ────────────────────────────────────────────────────────────────

class AuditLogRepo:
    """Append-only repository.  Provides no update or delete operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: AuditLog) -> AuditLog:
        self._session.add(record)
        await self._session.flush()
        return record

    async def find_by_id(self, log_id: uuid.UUID) -> AuditLog | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == ctx.org_id,
                AuditLog.id == log_id,
            )
        )
        return result.scalar_one_or_none()

    async def count(
        self,
        workspace_id: uuid.UUID,
        *,
        module: str | None = None,
        severity: str | None = None,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ) -> int:
        ctx = get_tenant_context()
        q = (
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.tenant_id == ctx.org_id,
                AuditLog.workspace_id == workspace_id,
            )
        )
        q = _apply_filters(q, module, severity, user_id, entity_type, entity_id, action, date_from, date_to, search)
        result = await self._session.execute(q)
        return result.scalar_one() or 0

    async def list_page(
        self,
        workspace_id: uuid.UUID,
        *,
        module: str | None = None,
        severity: str | None = None,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        ctx = get_tenant_context()
        q = select(AuditLog).where(
            AuditLog.tenant_id == ctx.org_id,
            AuditLog.workspace_id == workspace_id,
        )
        q = _apply_filters(q, module, severity, user_id, entity_type, entity_id, action, date_from, date_to, search)
        if cursor:
            cursor_ts, cursor_id = _decode_audit_cursor(cursor)
            q = q.where(
                or_(
                    AuditLog.created_at < cursor_ts,
                    (AuditLog.created_at == cursor_ts) & (AuditLog.id < cursor_id),
                )
            )
        q = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        workspace_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditLog]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == ctx.org_id,
                AuditLog.workspace_id == workspace_id,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditLog]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == ctx.org_id,
                AuditLog.workspace_id == workspace_id,
                AuditLog.user_id == user_id,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_module(
        self,
        module: str,
        workspace_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditLog]:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == ctx.org_id,
                AuditLog.workspace_id == workspace_id,
                AuditLog.module == module,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_statistics(
        self, workspace_id: uuid.UUID, period_days: int = 30
    ) -> AuditStatisticsOut:
        ctx = get_tenant_context()
        cutoff = datetime.now(UTC) - timedelta(days=period_days)
        base = [
            AuditLog.tenant_id == ctx.org_id,
            AuditLog.workspace_id == workspace_id,
            AuditLog.created_at >= cutoff,
        ]

        total_res = await self._session.execute(
            select(func.count()).select_from(AuditLog).where(*base)
        )
        total = total_res.scalar_one() or 0

        sev_res = await self._session.execute(
            select(AuditLog.severity, func.count()).where(*base).group_by(AuditLog.severity)
        )
        by_severity = {row[0]: row[1] for row in sev_res.all()}

        mod_res = await self._session.execute(
            select(AuditLog.module, func.count()).where(*base).group_by(AuditLog.module)
        )
        by_module = {row[0]: row[1] for row in mod_res.all()}

        act_res = await self._session.execute(
            select(AuditLog.action, func.count())
            .where(*base)
            .group_by(AuditLog.action)
            .order_by(func.count().desc())
            .limit(10)
        )
        by_action = {row[0]: row[1] for row in act_res.all()}

        return AuditStatisticsOut(
            total_events=total,
            by_severity=by_severity,
            by_module=by_module,
            by_action=by_action,
            period_days=period_days,
        )


# ── Private filter helper ─────────────────────────────────────────────────────

def _apply_filters(
    q: Any,
    module: str | None,
    severity: str | None,
    user_id: uuid.UUID | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    action: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    search: str | None,
) -> Any:
    if module:
        q = q.where(AuditLog.module == module)
    if severity:
        q = q.where(AuditLog.severity == severity)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if action:
        q = q.where(AuditLog.action == action)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    if search:
        term = f"%{search}%"
        q = q.where(
            or_(
                AuditLog.action.ilike(term),
                AuditLog.module.ilike(term),
                AuditLog.entity_type.ilike(term),
            )
        )
    return q
