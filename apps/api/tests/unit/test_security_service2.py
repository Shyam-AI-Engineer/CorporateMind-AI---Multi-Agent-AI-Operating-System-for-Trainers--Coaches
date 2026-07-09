"""Backend unit tests — Sprint 58: Security Center (part 2).

Covers: get_security_summary (cache hit/miss/degraded/scoring),
        get_security_alerts (cache hit/miss, all alert rules).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.security.schemas import (
    RoleCount,
    RoleDistributionOut,
    SecurityAlert,
    SecurityAlertsOut,
    SecuritySummaryOut,
)
from corpmind.modules.security.service import (
    SecurityCenterService,
    _CACHE_TTL,
    _MAX_SAFE_ADMINS,
    _alerts_cache_key,
    _summary_cache_key,
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


# ── get_security_summary — cache hit ─────────────────────────────────────────

class TestGetSecuritySummaryCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self) -> None:
        cached = SecuritySummaryOut(
            overall_security_score=0.9,
            active_api_keys=5,
            expired_api_keys=0,
            active_workspace_members=8,
            organization_admins=2,
            audit_events_today=10,
            critical_audit_events=0,
            checked_at=NOW,
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached.model_dump_json()
        session = _make_session()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()

        assert result.overall_security_score == 0.9
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_db_on_cache_hit(self) -> None:
        cached = SecuritySummaryOut(
            overall_security_score=1.0,
            active_api_keys=0,
            expired_api_keys=0,
            active_workspace_members=0,
            organization_admins=0,
            audit_events_today=0,
            critical_audit_events=0,
            checked_at=NOW,
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached.model_dump_json()
        session = _make_session()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_security_summary()

        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_key_uses_org_id(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        # 3 queries in order: members, api_keys, audit
        session.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=(5, 2))),
            MagicMock(fetchone=MagicMock(return_value=(3, 0, 0))),
            MagicMock(fetchone=MagicMock(return_value=(10, 0))),
        ]

        with patch(_PATCH_CTX, return_value=_ctx("org-555")), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_security_summary()

        cache_key = mock_redis.get.call_args[0][0]
        assert "org-555" in cache_key


# ── get_security_summary — cache miss / scoring ───────────────────────────────

class TestGetSecuritySummaryScoring:
    def _setup(
        self,
        *,
        active_members: int = 5,
        org_admins: int = 2,
        active_keys: int = 3,
        expired_keys: int = 0,
        never_used_keys: int = 0,
        events_today: int = 5,
        critical_events: int = 0,
    ) -> tuple[AsyncMock, AsyncMock]:
        """Build a mock session with 3 separate fetchone returns."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        session = _make_session()
        # The service makes 3 execute() calls in order:
        # 1. workspace_members → (active_members, org_admins)
        # 2. api_keys          → (active_keys, expired_keys, never_used_keys)
        # 3. audit_logs        → (events_today, critical_events)
        results = [
            MagicMock(fetchone=MagicMock(return_value=(active_members, org_admins))),
            MagicMock(fetchone=MagicMock(return_value=(active_keys, expired_keys, never_used_keys))),
            MagicMock(fetchone=MagicMock(return_value=(events_today, critical_events))),
        ]
        session.execute.side_effect = results
        return session, mock_redis

    @pytest.mark.asyncio
    async def test_perfect_score_when_no_issues(self) -> None:
        session, mock_redis = self._setup(
            org_admins=2, expired_keys=0, never_used_keys=0, critical_events=0
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.overall_security_score == 1.0

    @pytest.mark.asyncio
    async def test_score_deducted_for_expired_keys(self) -> None:
        session, mock_redis = self._setup(
            expired_keys=2, never_used_keys=0, critical_events=0, org_admins=2
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.overall_security_score == 0.7

    @pytest.mark.asyncio
    async def test_score_deducted_for_critical_events(self) -> None:
        session, mock_redis = self._setup(
            expired_keys=0, never_used_keys=0, critical_events=1, org_admins=2
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.overall_security_score == 0.8

    @pytest.mark.asyncio
    async def test_score_deducted_for_never_used_keys(self) -> None:
        session, mock_redis = self._setup(
            expired_keys=0, never_used_keys=1, critical_events=0, org_admins=2
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.overall_security_score == 0.9

    @pytest.mark.asyncio
    async def test_score_deducted_for_no_admins(self) -> None:
        session, mock_redis = self._setup(
            org_admins=0, expired_keys=0, never_used_keys=0, critical_events=0
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.overall_security_score == 0.9

    @pytest.mark.asyncio
    async def test_score_all_deductions_combined(self) -> None:
        session, mock_redis = self._setup(
            org_admins=0, expired_keys=2, never_used_keys=1, critical_events=3
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        # 1.0 - 0.3 - 0.2 - 0.1 - 0.1 = 0.3
        assert result.overall_security_score == 0.3

    @pytest.mark.asyncio
    async def test_score_never_goes_below_zero(self) -> None:
        session, mock_redis = self._setup(
            org_admins=0, expired_keys=10, never_used_keys=5, critical_events=10
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.overall_security_score >= 0.0

    @pytest.mark.asyncio
    async def test_active_api_keys_populated(self) -> None:
        session, mock_redis = self._setup(active_keys=7)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.active_api_keys == 7

    @pytest.mark.asyncio
    async def test_audit_events_today_populated(self) -> None:
        session, mock_redis = self._setup(events_today=20)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.audit_events_today == 20

    @pytest.mark.asyncio
    async def test_stores_in_cache(self) -> None:
        session, mock_redis = self._setup()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_security_summary()
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == _CACHE_TTL

    @pytest.mark.asyncio
    async def test_graceful_redis_get_error(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("redis down")
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=(5, 2))),
            MagicMock(fetchone=MagicMock(return_value=(3, 0, 0))),
            MagicMock(fetchone=MagicMock(return_value=(10, 0))),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()

        assert result.overall_security_score == 1.0

    @pytest.mark.asyncio
    async def test_graceful_redis_setex_error(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("redis write error")
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=(5, 2))),
            MagicMock(fetchone=MagicMock(return_value=(3, 0, 0))),
            MagicMock(fetchone=MagicMock(return_value=(10, 0))),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()

        assert isinstance(result, SecuritySummaryOut)

    @pytest.mark.asyncio
    async def test_handles_none_rows(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=None)),
            MagicMock(fetchone=MagicMock(return_value=None)),
            MagicMock(fetchone=MagicMock(return_value=None)),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()

        assert result.active_api_keys == 0
        assert result.organization_admins == 0

    @pytest.mark.asyncio
    async def test_returns_security_summary_out_type(self) -> None:
        session, mock_redis = self._setup()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert isinstance(result, SecuritySummaryOut)

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self) -> None:
        session, mock_redis = self._setup()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_summary()
        assert result.checked_at.tzinfo is not None


# ── get_security_alerts — cache hit ──────────────────────────────────────────

class TestGetSecurityAlertsCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_alerts(self) -> None:
        cached = SecurityAlertsOut(
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
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached.model_dump_json()
        session = _make_session()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()

        assert result.total == 1
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_db_on_cache_hit(self) -> None:
        cached = SecurityAlertsOut(alerts=[], total=0, checked_at=NOW)
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached.model_dump_json()
        session = _make_session()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_security_alerts()

        session.execute.assert_not_called()


# ── get_security_alerts — alert rules ────────────────────────────────────────

class TestGetSecurityAlertRules:
    def _setup(
        self,
        *,
        expired_keys: int = 0,
        never_used_keys: int = 0,
        total_keys: int = 0,
        org_admins: int = 2,
        pending_invites: int = 0,
        critical_today: int = 0,
    ) -> tuple[AsyncMock, AsyncMock]:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        session = _make_session()
        # 3 execute() calls in order: api_keys, workspace_members, audit_logs
        results = [
            MagicMock(fetchone=MagicMock(return_value=(expired_keys, never_used_keys, total_keys))),
            MagicMock(fetchone=MagicMock(return_value=(org_admins, pending_invites))),
            MagicMock(fetchone=MagicMock(return_value=(critical_today,))),
        ]
        session.execute.side_effect = results
        return session, mock_redis

    @pytest.mark.asyncio
    async def test_no_alerts_when_clean(self) -> None:
        session, mock_redis = self._setup(
            org_admins=2, expired_keys=0, never_used_keys=0,
            total_keys=3, critical_today=0, pending_invites=0
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        assert result.total == 0
        assert result.alerts == []

    @pytest.mark.asyncio
    async def test_expired_key_alert_generated(self) -> None:
        session, mock_redis = self._setup(expired_keys=3, total_keys=5)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "expired_api_keys" in types

    @pytest.mark.asyncio
    async def test_expired_key_alert_severity_high(self) -> None:
        session, mock_redis = self._setup(expired_keys=1, total_keys=2)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "expired_api_keys")
        assert alert.severity == "high"
        assert alert.count == 1

    @pytest.mark.asyncio
    async def test_critical_audit_alert_generated(self) -> None:
        session, mock_redis = self._setup(critical_today=5)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "critical_audit_events" in types

    @pytest.mark.asyncio
    async def test_critical_audit_alert_severity_critical(self) -> None:
        session, mock_redis = self._setup(critical_today=2)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "critical_audit_events")
        assert alert.severity == "critical"

    @pytest.mark.asyncio
    async def test_no_admin_alert_generated_when_keys_exist(self) -> None:
        session, mock_redis = self._setup(org_admins=0, total_keys=2)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "no_admin_user" in types

    @pytest.mark.asyncio
    async def test_no_admin_alert_not_generated_when_no_keys(self) -> None:
        # no_admin_user only fires if there are keys (org exists and is configured)
        session, mock_redis = self._setup(org_admins=0, total_keys=0)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "no_admin_user" not in types

    @pytest.mark.asyncio
    async def test_no_admin_alert_severity_critical(self) -> None:
        session, mock_redis = self._setup(org_admins=0, total_keys=1)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "no_admin_user")
        assert alert.severity == "critical"

    @pytest.mark.asyncio
    async def test_excessive_admins_alert_generated(self) -> None:
        session, mock_redis = self._setup(org_admins=_MAX_SAFE_ADMINS + 1)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "excessive_admins" in types

    @pytest.mark.asyncio
    async def test_excessive_admins_not_generated_at_threshold(self) -> None:
        session, mock_redis = self._setup(org_admins=_MAX_SAFE_ADMINS)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "excessive_admins" not in types

    @pytest.mark.asyncio
    async def test_excessive_admins_alert_severity_medium(self) -> None:
        session, mock_redis = self._setup(org_admins=_MAX_SAFE_ADMINS + 2)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "excessive_admins")
        assert alert.severity == "medium"

    @pytest.mark.asyncio
    async def test_never_used_keys_alert_generated(self) -> None:
        session, mock_redis = self._setup(never_used_keys=2)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "unused_api_keys" in types

    @pytest.mark.asyncio
    async def test_never_used_keys_alert_severity_low(self) -> None:
        session, mock_redis = self._setup(never_used_keys=1)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "unused_api_keys")
        assert alert.severity == "low"

    @pytest.mark.asyncio
    async def test_pending_invites_alert_generated(self) -> None:
        session, mock_redis = self._setup(pending_invites=3)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        types = [a.alert_type for a in result.alerts]
        assert "pending_invitations" in types

    @pytest.mark.asyncio
    async def test_pending_invites_alert_severity_low(self) -> None:
        session, mock_redis = self._setup(pending_invites=2)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "pending_invitations")
        assert alert.severity == "low"
        assert alert.count == 2

    @pytest.mark.asyncio
    async def test_total_equals_alert_count(self) -> None:
        session, mock_redis = self._setup(
            expired_keys=1, critical_today=2, never_used_keys=1, total_keys=3
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        assert result.total == len(result.alerts)

    @pytest.mark.asyncio
    async def test_stores_result_in_cache(self) -> None:
        session, mock_redis = self._setup()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_security_alerts()
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[1] == _CACHE_TTL

    @pytest.mark.asyncio
    async def test_graceful_redis_get_error(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("redis down")
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=(0, 0, 0))),
            MagicMock(fetchone=MagicMock(return_value=(2, 0))),
            MagicMock(fetchone=MagicMock(return_value=(0,))),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()

        assert isinstance(result, SecurityAlertsOut)

    @pytest.mark.asyncio
    async def test_graceful_redis_setex_error(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("write error")
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=(0, 0, 0))),
            MagicMock(fetchone=MagicMock(return_value=(2, 0))),
            MagicMock(fetchone=MagicMock(return_value=(0,))),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()

        assert isinstance(result, SecurityAlertsOut)

    @pytest.mark.asyncio
    async def test_handles_none_rows(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=None)),
            MagicMock(fetchone=MagicMock(return_value=None)),
            MagicMock(fetchone=MagicMock(return_value=None)),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_returns_security_alerts_out_type(self) -> None:
        session, mock_redis = self._setup()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        assert isinstance(result, SecurityAlertsOut)

    @pytest.mark.asyncio
    async def test_alert_count_in_message(self) -> None:
        session, mock_redis = self._setup(expired_keys=5, total_keys=5)
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        alert = next(a for a in result.alerts if a.alert_type == "expired_api_keys")
        assert "5" in alert.message

    @pytest.mark.asyncio
    async def test_checked_at_is_utc(self) -> None:
        session, mock_redis = self._setup()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()
        assert result.checked_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_cache_key_uses_org_id(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        session = _make_session()
        results = [
            MagicMock(fetchone=MagicMock(return_value=(0, 0, 0))),
            MagicMock(fetchone=MagicMock(return_value=(2, 0))),
            MagicMock(fetchone=MagicMock(return_value=(0,))),
        ]
        session.execute.side_effect = results

        with patch(_PATCH_CTX, return_value=_ctx("org-alert-99")), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            await svc.get_security_alerts()

        cache_key = mock_redis.get.call_args[0][0]
        assert "org-alert-99" in cache_key

    @pytest.mark.asyncio
    async def test_all_rules_can_trigger_simultaneously(self) -> None:
        session, mock_redis = self._setup(
            expired_keys=2,
            never_used_keys=3,
            total_keys=5,
            org_admins=_MAX_SAFE_ADMINS + 2,
            pending_invites=1,
            critical_today=1,
        )
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, return_value=mock_redis):
            svc = SecurityCenterService(session)
            result = await svc.get_security_alerts()

        types = {a.alert_type for a in result.alerts}
        assert "expired_api_keys" in types
        assert "critical_audit_events" in types
        assert "excessive_admins" in types
        assert "unused_api_keys" in types
        assert "pending_invitations" in types
        assert result.total == len(result.alerts)
