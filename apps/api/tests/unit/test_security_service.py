"""Backend unit tests — Sprint 58: Security Center (part 1).

Covers: schemas, cache key helpers, get_api_key_health, get_audit_summary,
        get_permission_overview, and get_role_distribution.

Pattern: session.execute.side_effect = [MagicMock(fetchX=MagicMock(return_value=...))]
Reason:  session = AsyncMock() makes session.execute.return_value also an AsyncMock,
         so .fetchone/.fetchall attributes are AsyncMock too — calling them returns
         coroutines.  Using side_effect with explicit MagicMock instances avoids this.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
from corpmind.modules.security.service import (
    SecurityCenterService,
    _alerts_cache_key,
    _roles_cache_key,
    _summary_cache_key,
    _CACHE_TTL,
    _MAX_SAFE_ADMINS,
    _TOP_MODULES_LIMIT,
)

_PATCH_CTX = "corpmind.modules.security.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.security.service.get_redis"

NOW = datetime(2026, 7, 9, 10, 0, 0, tzinfo=UTC)


def _ctx(org_id: str = "org-111") -> MagicMock:
    m = MagicMock()
    m.org_id = org_id
    return m


def _make_session() -> AsyncMock:
    return AsyncMock()


def _exec_one(row: tuple) -> MagicMock:
    """Return a mock execute result with fetchone returning `row`."""
    return MagicMock(fetchone=MagicMock(return_value=row))


def _exec_all(rows: list) -> MagicMock:
    """Return a mock execute result with fetchall returning `rows`."""
    return MagicMock(fetchall=MagicMock(return_value=rows))


# ── Schema tests ───────────────────────────────────────────────────────────────

class TestSecuritySummaryOutSchema:
    def test_fields_present(self) -> None:
        s = SecuritySummaryOut(
            overall_security_score=0.9,
            active_api_keys=5,
            expired_api_keys=0,
            active_workspace_members=10,
            organization_admins=2,
            audit_events_today=15,
            critical_audit_events=0,
            checked_at=NOW,
        )
        assert s.overall_security_score == 0.9
        assert s.active_api_keys == 5
        assert s.organization_admins == 2

    def test_score_clamp_above_one(self) -> None:
        s = SecuritySummaryOut(
            overall_security_score=1.5,
            active_api_keys=0,
            expired_api_keys=0,
            active_workspace_members=0,
            organization_admins=0,
            audit_events_today=0,
            critical_audit_events=0,
            checked_at=NOW,
        )
        assert s.overall_security_score == 1.0

    def test_score_clamp_below_zero(self) -> None:
        s = SecuritySummaryOut(
            overall_security_score=-0.5,
            active_api_keys=0,
            expired_api_keys=0,
            active_workspace_members=0,
            organization_admins=0,
            audit_events_today=0,
            critical_audit_events=0,
            checked_at=NOW,
        )
        assert s.overall_security_score == 0.0

    def test_score_zero_valid(self) -> None:
        s = SecuritySummaryOut(
            overall_security_score=0.0,
            active_api_keys=0,
            expired_api_keys=0,
            active_workspace_members=0,
            organization_admins=0,
            audit_events_today=0,
            critical_audit_events=0,
            checked_at=NOW,
        )
        assert s.overall_security_score == 0.0

    def test_score_one_valid(self) -> None:
        s = SecuritySummaryOut(
            overall_security_score=1.0,
            active_api_keys=0,
            expired_api_keys=0,
            active_workspace_members=0,
            organization_admins=0,
            audit_events_today=0,
            critical_audit_events=0,
            checked_at=NOW,
        )
        assert s.overall_security_score == 1.0

    def test_model_dump_json_roundtrip(self) -> None:
        s = SecuritySummaryOut(
            overall_security_score=0.7,
            active_api_keys=3,
            expired_api_keys=1,
            active_workspace_members=8,
            organization_admins=2,
            audit_events_today=10,
            critical_audit_events=1,
            checked_at=NOW,
        )
        loaded = SecuritySummaryOut(**json.loads(s.model_dump_json()))
        assert loaded.overall_security_score == 0.7
        assert loaded.expired_api_keys == 1


class TestRoleCountSchema:
    def test_fields(self) -> None:
        rc = RoleCount(role="admin", count=3)
        assert rc.role == "admin"
        assert rc.count == 3


class TestRoleDistributionOutSchema:
    def test_empty_roles(self) -> None:
        rd = RoleDistributionOut(roles=[], total_members=0, checked_at=NOW)
        assert rd.total_members == 0
        assert len(rd.roles) == 0

    def test_multiple_roles(self) -> None:
        rd = RoleDistributionOut(
            roles=[
                RoleCount(role="owner", count=1),
                RoleCount(role="admin", count=2),
                RoleCount(role="member", count=5),
            ],
            total_members=8,
            checked_at=NOW,
        )
        assert rd.total_members == 8
        assert len(rd.roles) == 3

    def test_model_dump_json_roundtrip(self) -> None:
        rd = RoleDistributionOut(
            roles=[RoleCount(role="viewer", count=1)],
            total_members=1,
            checked_at=NOW,
        )
        loaded = RoleDistributionOut(**json.loads(rd.model_dump_json()))
        assert loaded.roles[0].role == "viewer"


class TestApiKeyHealthOutSchema:
    def test_fields(self) -> None:
        ak = ApiKeyHealthOut(
            total_keys=10,
            active=8,
            expired=2,
            never_used=3,
            used_last_30_days=5,
            checked_at=NOW,
        )
        assert ak.total_keys == 10
        assert ak.expired == 2
        assert ak.never_used == 3

    def test_zero_fields(self) -> None:
        ak = ApiKeyHealthOut(
            total_keys=0,
            active=0,
            expired=0,
            never_used=0,
            used_last_30_days=0,
            checked_at=NOW,
        )
        assert ak.total_keys == 0

    def test_model_dump_json_roundtrip(self) -> None:
        ak = ApiKeyHealthOut(
            total_keys=4,
            active=3,
            expired=1,
            never_used=1,
            used_last_30_days=2,
            checked_at=NOW,
        )
        loaded = ApiKeyHealthOut(**json.loads(ak.model_dump_json()))
        assert loaded.active == 3


class TestModuleAuditEntrySchema:
    def test_fields(self) -> None:
        m = ModuleAuditEntry(module="billing", event_count=10)
        assert m.module == "billing"
        assert m.event_count == 10


class TestAuditSummaryOutSchema:
    def test_empty_top_modules(self) -> None:
        a = AuditSummaryOut(
            events_today=0,
            critical_events=0,
            warning_events=0,
            top_modules=[],
            checked_at=NOW,
        )
        assert a.events_today == 0
        assert len(a.top_modules) == 0

    def test_with_modules(self) -> None:
        a = AuditSummaryOut(
            events_today=20,
            critical_events=2,
            warning_events=3,
            top_modules=[ModuleAuditEntry(module="crm", event_count=10)],
            checked_at=NOW,
        )
        assert a.critical_events == 2
        assert a.top_modules[0].module == "crm"

    def test_model_dump_json_roundtrip(self) -> None:
        a = AuditSummaryOut(
            events_today=5,
            critical_events=1,
            warning_events=2,
            top_modules=[ModuleAuditEntry(module="training", event_count=3)],
            checked_at=NOW,
        )
        loaded = AuditSummaryOut(**json.loads(a.model_dump_json()))
        assert loaded.critical_events == 1


class TestWorkspacePermissionRowSchema:
    def test_fields(self) -> None:
        w = WorkspacePermissionRow(
            workspace_id="ws-1",
            owners=1,
            admins=2,
            members=5,
            viewers=0,
        )
        assert w.owners == 1
        assert w.viewers == 0


class TestPermissionOverviewOutSchema:
    def test_empty_workspaces(self) -> None:
        p = PermissionOverviewOut(workspaces=[], total_workspaces=0, checked_at=NOW)
        assert p.total_workspaces == 0

    def test_with_workspace(self) -> None:
        p = PermissionOverviewOut(
            workspaces=[
                WorkspacePermissionRow(
                    workspace_id="ws-1", owners=1, admins=1, members=3, viewers=0
                )
            ],
            total_workspaces=1,
            checked_at=NOW,
        )
        assert p.total_workspaces == 1
        assert p.workspaces[0].members == 3


class TestSecurityAlertSchema:
    def test_fields(self) -> None:
        a = SecurityAlert(
            alert_type="expired_api_keys",
            severity="high",
            message="1 key expired.",
            count=1,
        )
        assert a.severity == "high"
        assert a.count == 1


class TestSecurityAlertsOutSchema:
    def test_empty_alerts(self) -> None:
        out = SecurityAlertsOut(alerts=[], total=0, checked_at=NOW)
        assert out.total == 0

    def test_with_alerts(self) -> None:
        out = SecurityAlertsOut(
            alerts=[
                SecurityAlert(
                    alert_type="expired_api_keys",
                    severity="high",
                    message="1 key expired.",
                    count=1,
                )
            ],
            total=1,
            checked_at=NOW,
        )
        assert out.total == 1

    def test_model_dump_json_roundtrip(self) -> None:
        out = SecurityAlertsOut(alerts=[], total=0, checked_at=NOW)
        loaded = SecurityAlertsOut(**json.loads(out.model_dump_json()))
        assert loaded.total == 0


# ── Cache key helpers ──────────────────────────────────────────────────────────

class TestCacheKeyHelpers:
    def test_summary_key(self) -> None:
        assert _summary_cache_key("org-1") == "t:org-1:security:summary"

    def test_roles_key(self) -> None:
        assert _roles_cache_key("org-2") == "t:org-2:security:roles"

    def test_alerts_key(self) -> None:
        assert _alerts_cache_key("org-3") == "t:org-3:security:alerts"

    def test_summary_key_unique_per_org(self) -> None:
        assert _summary_cache_key("org-A") != _summary_cache_key("org-B")

    def test_roles_key_unique_per_org(self) -> None:
        assert _roles_cache_key("org-A") != _roles_cache_key("org-B")

    def test_alerts_key_unique_per_org(self) -> None:
        assert _alerts_cache_key("org-A") != _alerts_cache_key("org-B")

    def test_different_keys_for_same_org(self) -> None:
        org = "org-X"
        assert _summary_cache_key(org) != _roles_cache_key(org)
        assert _roles_cache_key(org) != _alerts_cache_key(org)
        assert _summary_cache_key(org) != _alerts_cache_key(org)


# ── Constants ──────────────────────────────────────────────────────────────────

class TestConstants:
    def test_cache_ttl(self) -> None:
        assert _CACHE_TTL == 300

    def test_max_safe_admins(self) -> None:
        assert _MAX_SAFE_ADMINS > 0

    def test_top_modules_limit(self) -> None:
        assert _TOP_MODULES_LIMIT > 0


# ── get_api_key_health ─────────────────────────────────────────────────────────

class TestGetApiKeyHealth:
    @pytest.mark.asyncio
    async def test_returns_correct_counts(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((10, 8, 2, 3, 5))]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert result.total_keys == 10
        assert result.active == 8
        assert result.expired == 2
        assert result.never_used == 3
        assert result.used_last_30_days == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_keys(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((0, 0, 0, 0, 0))]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert result.total_keys == 0
        assert result.expired == 0

    @pytest.mark.asyncio
    async def test_handles_none_row(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one(None)]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert result.total_keys == 0

    @pytest.mark.asyncio
    async def test_handles_null_values(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((None, None, None, None, None))]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert result.total_keys == 0
        assert result.active == 0

    @pytest.mark.asyncio
    async def test_uses_correct_tenant_id(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((0, 0, 0, 0, 0))]

        with patch(_PATCH_CTX, return_value=_ctx("org-abc")):
            svc = SecurityCenterService(session)
            await svc.get_api_key_health()

        call_kwargs = session.execute.call_args[0][1]
        assert call_kwargs["tenant_id"] == "org-abc"

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((0, 0, 0, 0, 0))]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert result.checked_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_returns_api_key_health_out_type(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((5, 5, 0, 0, 5))]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert isinstance(result, ApiKeyHealthOut)

    @pytest.mark.asyncio
    async def test_used_last_30_days_count(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_one((10, 10, 0, 2, 8))]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_api_key_health()

        assert result.used_last_30_days == 8


# ── get_audit_summary ──────────────────────────────────────────────────────────

class TestGetAuditSummary:
    @pytest.mark.asyncio
    async def test_returns_correct_counts(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((30, 3, 7)),
            _exec_all([("billing", 10), ("crm", 8), ("training", 6)]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert result.events_today == 30
        assert result.critical_events == 3
        assert result.warning_events == 7

    @pytest.mark.asyncio
    async def test_top_modules_populated(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((10, 1, 2)),
            _exec_all([("billing", 5), ("crm", 3)]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert len(result.top_modules) == 2
        assert result.top_modules[0].module == "billing"
        assert result.top_modules[0].event_count == 5

    @pytest.mark.asyncio
    async def test_empty_audit_log(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((0, 0, 0)),
            _exec_all([]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert result.events_today == 0
        assert result.top_modules == []

    @pytest.mark.asyncio
    async def test_handles_none_row(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one(None),
            _exec_all([]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert result.events_today == 0
        assert result.critical_events == 0

    @pytest.mark.asyncio
    async def test_handles_null_values_in_row(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((None, None, None)),
            _exec_all([]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert result.events_today == 0
        assert result.warning_events == 0

    @pytest.mark.asyncio
    async def test_uses_correct_tenant_id(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((0, 0, 0)),
            _exec_all([]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx("org-xyz")):
            svc = SecurityCenterService(session)
            await svc.get_audit_summary()

        first_call_kwargs = session.execute.call_args_list[0][0][1]
        assert first_call_kwargs["tenant_id"] == "org-xyz"

    @pytest.mark.asyncio
    async def test_returns_audit_summary_out_type(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((0, 0, 0)),
            _exec_all([]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert isinstance(result, AuditSummaryOut)

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((0, 0, 0)),
            _exec_all([]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert result.checked_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_module_entry_types(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_one((5, 0, 0)),
            _exec_all([("admin", 5)]),
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_audit_summary()

        assert isinstance(result.top_modules[0], ModuleAuditEntry)


# ── get_permission_overview ────────────────────────────────────────────────────

class TestGetPermissionOverview:
    @pytest.mark.asyncio
    async def test_returns_per_workspace_rows(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_all([
                ("ws-1", "owner", 1),
                ("ws-1", "admin", 2),
                ("ws-1", "member", 5),
                ("ws-2", "member", 3),
            ])
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert result.total_workspaces == 2
        ws1 = next(w for w in result.workspaces if w.workspace_id == "ws-1")
        assert ws1.owners == 1
        assert ws1.admins == 2
        assert ws1.members == 5
        assert ws1.viewers == 0

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert result.total_workspaces == 0
        assert result.workspaces == []

    @pytest.mark.asyncio
    async def test_single_workspace_single_role(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_all([("ws-only", "viewer", 4)])
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert result.total_workspaces == 1
        ws = result.workspaces[0]
        assert ws.viewers == 4
        assert ws.owners == 0

    @pytest.mark.asyncio
    async def test_uses_correct_tenant_id(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx("org-perm")):
            svc = SecurityCenterService(session)
            await svc.get_permission_overview()

        call_kwargs = session.execute.call_args[0][1]
        assert call_kwargs["tenant_id"] == "org-perm"

    @pytest.mark.asyncio
    async def test_returns_permission_overview_out_type(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert isinstance(result, PermissionOverviewOut)

    @pytest.mark.asyncio
    async def test_workspace_row_type(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_all([("ws-typed", "admin", 1)])]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert isinstance(result.workspaces[0], WorkspacePermissionRow)

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self) -> None:
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert result.checked_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_multiple_workspaces(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_all([
                ("ws-a", "owner", 1),
                ("ws-b", "member", 3),
                ("ws-c", "viewer", 2),
            ])
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert result.total_workspaces == 3

    @pytest.mark.asyncio
    async def test_all_roles_aggregated_per_workspace(self) -> None:
        session = _make_session()
        session.execute.side_effect = [
            _exec_all([
                ("ws-full", "owner", 2),
                ("ws-full", "admin", 3),
                ("ws-full", "member", 10),
                ("ws-full", "viewer", 5),
            ])
        ]

        with patch(_PATCH_CTX, return_value=_ctx()):
            svc = SecurityCenterService(session)
            result = await svc.get_permission_overview()

        assert result.total_workspaces == 1
        ws = result.workspaces[0]
        assert ws.owners == 2
        assert ws.admins == 3
        assert ws.members == 10
        assert ws.viewers == 5


# ── get_role_distribution cache hit ───────────────────────────────────────────

class TestGetRoleDistributionCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self) -> None:
        cached_data = RoleDistributionOut(
            roles=[RoleCount(role="admin", count=2)],
            total_members=2,
            checked_at=NOW,
        )

        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached_data.model_dump_json()

        session = _make_session()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert result.total_members == 2
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_db_on_cache_hit(self) -> None:
        cached_data = RoleDistributionOut(
            roles=[], total_members=0, checked_at=NOW
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached_data.model_dump_json()
        session = _make_session()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_role_distribution()

        session.execute.assert_not_called()


class TestGetRoleDistributionCacheMiss:
    @pytest.mark.asyncio
    async def test_queries_db_on_cache_miss(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [
            _exec_all([("owner", 1), ("member", 4)])
        ]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert result.total_members == 5
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_result_in_cache(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_role_distribution()

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == _CACHE_TTL

    @pytest.mark.asyncio
    async def test_role_counts_correct(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [
            _exec_all([("owner", 1), ("admin", 3), ("member", 5), ("viewer", 2)])
        ]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert result.total_members == 11
        roles_map = {rc.role: rc.count for rc in result.roles}
        assert roles_map["owner"] == 1
        assert roles_map["admin"] == 3

    @pytest.mark.asyncio
    async def test_empty_workspace_members(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert result.total_members == 0
        assert result.roles == []

    @pytest.mark.asyncio
    async def test_graceful_redis_miss_on_get_error(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("redis down")
        session = _make_session()
        session.execute.side_effect = [_exec_all([("member", 2)])]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert result.total_members == 2

    @pytest.mark.asyncio
    async def test_graceful_redis_error_on_setex(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("redis write error")
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert result.total_members == 0

    @pytest.mark.asyncio
    async def test_cache_key_uses_org_id(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx("org-777")), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_role_distribution()

        cache_key = mock_redis.get.call_args[0][0]
        assert "org-777" in cache_key

    @pytest.mark.asyncio
    async def test_returns_role_distribution_out_type(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [_exec_all([])]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert isinstance(result, RoleDistributionOut)

    @pytest.mark.asyncio
    async def test_role_count_objects(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        session.execute.side_effect = [_exec_all([("admin", 4)])]

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_role_distribution()

        assert isinstance(result.roles[0], RoleCount)
