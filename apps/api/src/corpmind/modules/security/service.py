"""Security Center & Access Governance service — Sprint 58.

All methods are READ-ONLY.  No writes, no mutations, no background tasks.
Cross-module data accessed via sqlalchemy.text() raw SQL — never importing
other modules' models or repos.

Security score formula:
  score = 1.0
  - 0.3  if expired_api_keys > 0
  - 0.2  if critical_audit_events today > 0
  - 0.1  if never_used_keys > 0
  - 0.1  if org_admins == 0
  clamped to [0.0, 1.0]

Alerts are deterministic rule-based checks — no AI, no LLM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.security.schemas import (
    ApiKeyHealthOut,
    AuditSummaryOut,
    ModuleAuditEntry,
    PermissionOverviewOut,
    RoleCount,
    RoleDistributionOut,
    SecurityAlert,
    SecurityAlertsOut,
    SecuritySummaryOut,
    WorkspacePermissionRow,
)

log = structlog.get_logger(__name__)

_CACHE_TTL = 300  # seconds

# ── Alert thresholds ──────────────────────────────────────────────────────────

_MAX_SAFE_ADMINS = 5  # warn when admin+owner count exceeds this
_TOP_MODULES_LIMIT = 5


def _summary_cache_key(org_id: object) -> str:
    return f"t:{org_id}:security:summary"


def _roles_cache_key(org_id: object) -> str:
    return f"t:{org_id}:security:roles"


def _alerts_cache_key(org_id: object) -> str:
    return f"t:{org_id}:security:alerts"


class SecurityCenterService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_security_summary(self) -> SecuritySummaryOut:
        """Aggregate security posture; cached 5 minutes."""
        ctx = get_tenant_context()
        cache_key = _summary_cache_key(ctx.org_id)

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return SecuritySummaryOut(**json.loads(cached))
        except Exception:
            pass

        now = datetime.now(UTC)
        today_str = now.date().isoformat()

        member_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE removed_at IS NULL) AS active_members,
                        COUNT(*) FILTER (
                            WHERE role IN ('owner', 'admin') AND removed_at IS NULL
                        ) AS org_admins
                    FROM workspace_members
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchone()

        key_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE is_active = true) AS active_keys,
                        COUNT(*) FILTER (
                            WHERE expires_at IS NOT NULL AND expires_at < NOW()
                        ) AS expired_keys,
                        COUNT(*) FILTER (WHERE last_used_at IS NULL) AS never_used_keys
                    FROM api_keys
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchone()

        audit_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS events_today,
                        COUNT(*) FILTER (WHERE severity = 'critical') AS critical_events
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id
                      AND created_at >= :today
                    """
                ),
                {"tenant_id": str(ctx.org_id), "today": today_str},
            )
        ).fetchone()

        active_members = int(member_row[0] or 0) if member_row else 0
        org_admins = int(member_row[1] or 0) if member_row else 0
        active_keys = int(key_row[0] or 0) if key_row else 0
        expired_keys = int(key_row[1] or 0) if key_row else 0
        never_used_keys = int(key_row[2] or 0) if key_row else 0
        events_today = int(audit_row[0] or 0) if audit_row else 0
        critical_events = int(audit_row[1] or 0) if audit_row else 0

        score = 1.0
        if expired_keys > 0:
            score -= 0.3
        if critical_events > 0:
            score -= 0.2
        if never_used_keys > 0:
            score -= 0.1
        if org_admins == 0:
            score -= 0.1
        score = max(0.0, round(score, 2))

        result = SecuritySummaryOut(
            overall_security_score=score,
            active_api_keys=active_keys,
            expired_api_keys=expired_keys,
            active_workspace_members=active_members,
            organization_admins=org_admins,
            audit_events_today=events_today,
            critical_audit_events=critical_events,
            checked_at=now,
        )

        try:
            await get_redis().setex(cache_key, _CACHE_TTL, result.model_dump_json())
        except Exception:
            pass

        return result

    async def get_role_distribution(self) -> RoleDistributionOut:
        """Workspace member counts grouped by role; cached 5 minutes."""
        ctx = get_tenant_context()
        cache_key = _roles_cache_key(ctx.org_id)

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return RoleDistributionOut(**json.loads(cached))
        except Exception:
            pass

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT role, COUNT(*) AS cnt
                    FROM workspace_members
                    WHERE tenant_id = :tenant_id AND removed_at IS NULL
                    GROUP BY role
                    ORDER BY cnt DESC
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchall()

        role_counts = [RoleCount(role=str(r[0]), count=int(r[1])) for r in rows]
        total = sum(rc.count for rc in role_counts)

        result = RoleDistributionOut(
            roles=role_counts,
            total_members=total,
            checked_at=datetime.now(UTC),
        )

        try:
            await get_redis().setex(cache_key, _CACHE_TTL, result.model_dump_json())
        except Exception:
            pass

        return result

    async def get_api_key_health(self) -> ApiKeyHealthOut:
        """API key lifecycle health indicators (not cached — data freshness needed)."""
        ctx = get_tenant_context()

        row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_keys,
                        COUNT(*) FILTER (WHERE is_active = true) AS active_keys,
                        COUNT(*) FILTER (
                            WHERE expires_at IS NOT NULL AND expires_at < NOW()
                        ) AS expired_keys,
                        COUNT(*) FILTER (WHERE last_used_at IS NULL) AS never_used_keys,
                        COUNT(*) FILTER (
                            WHERE last_used_at >= NOW() - INTERVAL '30 days'
                        ) AS used_last_30d
                    FROM api_keys
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchone()

        return ApiKeyHealthOut(
            total_keys=int(row[0] or 0) if row else 0,
            active=int(row[1] or 0) if row else 0,
            expired=int(row[2] or 0) if row else 0,
            never_used=int(row[3] or 0) if row else 0,
            used_last_30_days=int(row[4] or 0) if row else 0,
            checked_at=datetime.now(UTC),
        )

    async def get_audit_summary(self) -> AuditSummaryOut:
        """Audit log summary for today, with top-5 modules."""
        ctx = get_tenant_context()
        now = datetime.now(UTC)
        today_str = now.date().isoformat()

        summary_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS events_today,
                        COUNT(*) FILTER (WHERE severity = 'critical') AS critical_events,
                        COUNT(*) FILTER (WHERE severity = 'warning') AS warning_events
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id AND created_at >= :today
                    """
                ),
                {"tenant_id": str(ctx.org_id), "today": today_str},
            )
        ).fetchone()

        module_rows = (
            await self._session.execute(
                text(
                    """
                    SELECT module, COUNT(*) AS cnt
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id AND created_at >= :today
                    GROUP BY module
                    ORDER BY cnt DESC
                    LIMIT :limit
                    """
                ),
                {
                    "tenant_id": str(ctx.org_id),
                    "today": today_str,
                    "limit": _TOP_MODULES_LIMIT,
                },
            )
        ).fetchall()

        return AuditSummaryOut(
            events_today=int(summary_row[0] or 0) if summary_row else 0,
            critical_events=int(summary_row[1] or 0) if summary_row else 0,
            warning_events=int(summary_row[2] or 0) if summary_row else 0,
            top_modules=[
                ModuleAuditEntry(module=str(r[0]), event_count=int(r[1]))
                for r in module_rows
            ],
            checked_at=now,
        )

    async def get_permission_overview(self) -> PermissionOverviewOut:
        """Per-workspace role breakdown (not cached)."""
        ctx = get_tenant_context()

        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        workspace_id::text,
                        role,
                        COUNT(*) AS cnt
                    FROM workspace_members
                    WHERE tenant_id = :tenant_id AND removed_at IS NULL
                    GROUP BY workspace_id, role
                    ORDER BY workspace_id, role
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchall()

        # Aggregate per workspace_id
        workspace_map: dict[str, dict[str, int]] = {}
        for ws_id, role, cnt in rows:
            if ws_id not in workspace_map:
                workspace_map[ws_id] = {"owner": 0, "admin": 0, "member": 0, "viewer": 0}
            workspace_map[ws_id][role] = int(cnt)

        workspaces = [
            WorkspacePermissionRow(
                workspace_id=ws_id,
                owners=counts.get("owner", 0),
                admins=counts.get("admin", 0),
                members=counts.get("member", 0),
                viewers=counts.get("viewer", 0),
            )
            for ws_id, counts in workspace_map.items()
        ]

        return PermissionOverviewOut(
            workspaces=workspaces,
            total_workspaces=len(workspaces),
            checked_at=datetime.now(UTC),
        )

    async def get_security_alerts(self) -> SecurityAlertsOut:
        """Deterministic rule-based security alerts; cached 5 minutes."""
        ctx = get_tenant_context()
        cache_key = _alerts_cache_key(ctx.org_id)

        try:
            cached = await get_redis().get(cache_key)
            if cached:
                return SecurityAlertsOut(**json.loads(cached))
        except Exception:
            pass

        now = datetime.now(UTC)
        today_str = now.date().isoformat()

        # Gather alert inputs in one pass per table
        key_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (
                            WHERE expires_at IS NOT NULL AND expires_at < NOW()
                        ) AS expired_keys,
                        COUNT(*) FILTER (WHERE last_used_at IS NULL) AS never_used_keys,
                        COUNT(*) AS total_keys
                    FROM api_keys
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchone()

        member_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (
                            WHERE role IN ('owner', 'admin') AND removed_at IS NULL
                        ) AS org_admins,
                        COUNT(*) FILTER (
                            WHERE accepted_at IS NULL AND removed_at IS NULL
                        ) AS pending_invites
                    FROM workspace_members
                    WHERE tenant_id = :tenant_id
                    """
                ),
                {"tenant_id": str(ctx.org_id)},
            )
        ).fetchone()

        audit_row = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE severity = 'critical') AS critical_today
                    FROM audit_logs
                    WHERE tenant_id = :tenant_id AND created_at >= :today
                    """
                ),
                {"tenant_id": str(ctx.org_id), "today": today_str},
            )
        ).fetchone()

        expired_keys = int(key_row[0] or 0) if key_row else 0
        never_used_keys = int(key_row[1] or 0) if key_row else 0
        total_keys = int(key_row[2] or 0) if key_row else 0
        org_admins = int(member_row[0] or 0) if member_row else 0
        pending_invites = int(member_row[1] or 0) if member_row else 0
        critical_today = int(audit_row[0] or 0) if audit_row else 0

        alerts: list[SecurityAlert] = []

        if expired_keys > 0:
            alerts.append(
                SecurityAlert(
                    alert_type="expired_api_keys",
                    severity="high",
                    message=f"{expired_keys} API key(s) have expired and should be rotated.",
                    count=expired_keys,
                )
            )

        if critical_today > 0:
            alerts.append(
                SecurityAlert(
                    alert_type="critical_audit_events",
                    severity="critical",
                    message=f"{critical_today} critical audit event(s) recorded today.",
                    count=critical_today,
                )
            )

        if org_admins == 0 and total_keys > 0:
            alerts.append(
                SecurityAlert(
                    alert_type="no_admin_user",
                    severity="critical",
                    message="No active workspace admins or owners found.",
                    count=0,
                )
            )

        if org_admins > _MAX_SAFE_ADMINS:
            alerts.append(
                SecurityAlert(
                    alert_type="excessive_admins",
                    severity="medium",
                    message=(
                        f"{org_admins} users have admin/owner access. "
                        f"Review whether all roles are necessary."
                    ),
                    count=org_admins,
                )
            )

        if never_used_keys > 0:
            alerts.append(
                SecurityAlert(
                    alert_type="unused_api_keys",
                    severity="low",
                    message=f"{never_used_keys} API key(s) have never been used.",
                    count=never_used_keys,
                )
            )

        if pending_invites > 0:
            alerts.append(
                SecurityAlert(
                    alert_type="pending_invitations",
                    severity="low",
                    message=f"{pending_invites} workspace invitation(s) are awaiting acceptance.",
                    count=pending_invites,
                )
            )

        result = SecurityAlertsOut(
            alerts=alerts,
            total=len(alerts),
            checked_at=now,
        )

        try:
            await get_redis().setex(cache_key, _CACHE_TTL, result.model_dump_json())
        except Exception:
            pass

        return result
