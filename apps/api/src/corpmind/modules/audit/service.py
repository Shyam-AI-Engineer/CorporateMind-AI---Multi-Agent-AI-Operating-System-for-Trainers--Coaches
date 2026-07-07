"""Audit log service — Sprint 53: Audit Log & Compliance Center."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.audit.events import AuditEventLogged
from corpmind.modules.audit.models import AuditLog
from corpmind.modules.audit.repo import AuditLogRepo, _encode_audit_cursor
from corpmind.modules.audit.schemas import (
    AUDIT_SEVERITIES,
    AuditLogCreate,
    AuditLogFilters,
    AuditLogListOut,
    AuditLogOut,
    AuditStatisticsOut,
)

log = structlog.get_logger(__name__)

# ── Cache config ──────────────────────────────────────────────────────────────

_AUDIT_LIST_TTL = 300
_AUDIT_DETAIL_TTL = 300
_AUDIT_STATS_TTL = 300


def _audit_list_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:audit:events:list"


def _audit_detail_key(org_id: uuid.UUID, log_id: uuid.UUID) -> str:
    return f"t:{org_id}:audit:events:detail:{log_id}"


def _audit_stats_key(org_id: uuid.UUID, ws_id: uuid.UUID) -> str:
    return f"t:{org_id}:{ws_id}:audit:statistics"


# ── Service ───────────────────────────────────────────────────────────────────

class AuditLogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AuditLogRepo(session)

    async def log_event(self, req: AuditLogCreate) -> AuditLogOut:
        """Insert an immutable audit entry.  Validates severity; busts caches."""
        if req.severity not in AUDIT_SEVERITIES:
            raise ValidationError(f"Invalid severity '{req.severity}'. Must be one of: {sorted(AUDIT_SEVERITIES)}")

        ctx = get_tenant_context()
        now = datetime.now(UTC)
        record = AuditLog(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            user_id=req.user_id,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            action=req.action,
            module=req.module,
            severity=req.severity,
            ip_address=req.ip_address,
            user_agent=req.user_agent,
            extra_data=req.metadata or {},
            created_at=now,
        )
        await self._repo.create(record)
        await self._session.commit()

        try:
            redis = get_redis()
            await redis.delete(_audit_list_key(ctx.org_id, req.workspace_id))
            await redis.delete(_audit_stats_key(ctx.org_id, req.workspace_id))
        except Exception:
            pass

        log.info(
            "audit.event_logged",
            log_id=str(record.id),
            action=req.action,
            module=req.module,
            severity=req.severity,
            tenant_id=str(ctx.org_id),
        )
        event = AuditEventLogged(
            log_id=record.id,
            action=req.action,
            module=req.module,
            severity=req.severity,
            tenant_id=ctx.org_id,
        )
        log.debug("audit.event", event_type=event.__class__.__name__)
        return AuditLogOut.model_validate(record)

    async def get_event(self, log_id: uuid.UUID) -> AuditLogOut:
        """Fetch a single audit entry by id, with Redis cache-aside."""
        ctx = get_tenant_context()
        key = _audit_detail_key(ctx.org_id, log_id)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                return AuditLogOut.model_validate_json(cached)
        except Exception:
            pass

        record = await self._repo.find_by_id(log_id)
        if not record:
            raise NotFoundError(f"Audit log {log_id} not found")

        out = AuditLogOut.model_validate(record)
        try:
            redis = get_redis()
            await redis.set(key, out.model_dump_json(), ex=_AUDIT_DETAIL_TTL)
        except Exception:
            pass
        return out

    async def list_events(self, filters: AuditLogFilters) -> AuditLogListOut:
        """Paginated event list.  Default (unfiltered) first page is Redis-cached."""
        ctx = get_tenant_context()
        is_default = (
            filters.module is None
            and filters.severity is None
            and filters.user_id is None
            and filters.entity_type is None
            and filters.entity_id is None
            and filters.action is None
            and filters.date_from is None
            and filters.date_to is None
            and filters.search is None
            and filters.cursor is None
        )

        if is_default:
            list_key = _audit_list_key(ctx.org_id, filters.workspace_id)
            try:
                redis = get_redis()
                cached = await redis.get(list_key)
                if cached:
                    return AuditLogListOut.model_validate_json(cached)
            except Exception:
                pass

        total = await self._repo.count(
            filters.workspace_id,
            module=filters.module,
            severity=filters.severity,
            user_id=filters.user_id,
            entity_type=filters.entity_type,
            entity_id=filters.entity_id,
            action=filters.action,
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=filters.search,
        )
        rows = await self._repo.list_page(
            filters.workspace_id,
            module=filters.module,
            severity=filters.severity,
            user_id=filters.user_id,
            entity_type=filters.entity_type,
            entity_id=filters.entity_id,
            action=filters.action,
            date_from=filters.date_from,
            date_to=filters.date_to,
            search=filters.search,
            cursor=filters.cursor,
            limit=filters.limit,
        )

        has_more = len(rows) > filters.limit
        page = rows[: filters.limit]
        next_cursor: str | None = None
        if has_more and page:
            last = page[-1]
            next_cursor = _encode_audit_cursor(last.created_at, last.id)

        out = AuditLogListOut(
            items=[AuditLogOut.model_validate(r) for r in page],
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
        )

        if is_default:
            try:
                redis = get_redis()
                await redis.set(list_key, out.model_dump_json(), ex=_AUDIT_LIST_TTL)
            except Exception:
                pass
        return out

    async def list_entity_events(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> list[AuditLogOut]:
        """All audit events for a specific entity — no cache (targeted query)."""
        rows = await self._repo.list_by_entity(entity_type, entity_id, workspace_id)
        return [AuditLogOut.model_validate(r) for r in rows]

    async def list_user_events(
        self, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> list[AuditLogOut]:
        """All audit events for a specific user — no cache."""
        rows = await self._repo.list_by_user(user_id, workspace_id)
        return [AuditLogOut.model_validate(r) for r in rows]

    async def list_module_events(
        self, module: str, workspace_id: uuid.UUID
    ) -> list[AuditLogOut]:
        """All recent audit events for a specific module — no cache."""
        rows = await self._repo.list_by_module(module, workspace_id)
        return [AuditLogOut.model_validate(r) for r in rows]

    async def get_statistics(
        self, workspace_id: uuid.UUID, period_days: int = 30
    ) -> AuditStatisticsOut:
        """Aggregate counts by severity / module / action.  Redis-cached TTL=300s."""
        ctx = get_tenant_context()
        key = _audit_stats_key(ctx.org_id, workspace_id)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                return AuditStatisticsOut.model_validate_json(cached)
        except Exception:
            pass

        stats = await self._repo.get_statistics(workspace_id, period_days=period_days)

        try:
            redis = get_redis()
            await redis.set(key, stats.model_dump_json(), ex=_AUDIT_STATS_TTL)
        except Exception:
            pass
        return stats
