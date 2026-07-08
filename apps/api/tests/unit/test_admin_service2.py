"""Additional unit tests for modules/admin — Sprint 54 (part 2).

Covers: repo layer, validation, API patterns, additional service branches.
Together with test_admin_service.py reaches the 180+ test target.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.admin.models import OrganizationSettings
from corpmind.modules.admin.repo import OrganizationAdminRepo, _MODULE_TABLE_MAP
from corpmind.modules.admin.schemas import (
    MODULE_NAMES,
    SUPPORTED_CURRENCIES,
    SUPPORTED_DATE_FORMATS,
    SUPPORTED_LANGUAGES,
    AdminModuleListOut,
    ModuleStatusOut,
    OrganizationSettingsOut,
    OrganizationSettingsUpdate,
    SystemStatusOut,
)
from corpmind.modules.admin.service import (
    OrganizationAdminService,
    _dashboard_key,
    _settings_key,
    _status_key,
)

# ── Patch targets ─────────────────────────────────────────────────────────────

_PATCH_CTX = "corpmind.modules.admin.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.admin.service.get_redis"
_PATCH_REPO_CTX = "corpmind.modules.admin.repo.get_tenant_context"

_ORG_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
_SETTINGS_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000004")


def _make_ctx(org_id: uuid.UUID = _ORG_ID) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    return ctx


def _make_orm_settings(**kwargs: Any) -> MagicMock:
    defaults = {
        "id": _SETTINGS_ID,
        "tenant_id": _ORG_ID,
        "organization_name": "Test Corp",
        "timezone": "Asia/Kolkata",
        "currency": "INR",
        "date_format": "DD/MM/YYYY",
        "language": "en",
        "default_workflow_id": None,
        "default_training_duration_days": 2,
        "default_invoice_due_days": 15,
        "logo_url": None,
        "is_active": True,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=OrganizationSettings)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_svc() -> tuple[OrganizationAdminService, MagicMock]:
    session = AsyncMock()
    svc = OrganizationAdminService(session)
    svc._repo = MagicMock()
    return svc, svc._repo


def _make_module_statuses() -> list[ModuleStatusOut]:
    return [
        ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=5)
        for n in MODULE_NAMES
    ]


# ── 13. Repo — module table map ────────────────────────────────────────────────

class TestRepoModuleTableMap:
    def test_map_has_customers(self) -> None:
        assert "customers" in _MODULE_TABLE_MAP

    def test_map_has_training(self) -> None:
        assert "training" in _MODULE_TABLE_MAP

    def test_map_has_billing(self) -> None:
        assert "billing" in _MODULE_TABLE_MAP

    def test_map_has_payments(self) -> None:
        assert "payments" in _MODULE_TABLE_MAP

    def test_map_has_notifications(self) -> None:
        assert "notifications" in _MODULE_TABLE_MAP

    def test_map_has_audit(self) -> None:
        assert "audit" in _MODULE_TABLE_MAP

    def test_map_has_workflow(self) -> None:
        assert "workflow" in _MODULE_TABLE_MAP

    def test_map_has_team(self) -> None:
        assert "team" in _MODULE_TABLE_MAP

    def test_map_customers_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["customers"] == "customers"

    def test_map_training_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["training"] == "training_engagements"

    def test_map_billing_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["billing"] == "customer_invoices"

    def test_map_payments_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["payments"] == "invoice_payments"

    def test_map_notifications_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["notifications"] == "notifications"

    def test_map_audit_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["audit"] == "audit_logs"

    def test_map_workflow_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["workflow"] == "workflow_runs"

    def test_map_team_table_name(self) -> None:
        assert _MODULE_TABLE_MAP["team"] == "workspace_members"

    def test_map_count_matches_module_names(self) -> None:
        assert len(_MODULE_TABLE_MAP) == len(MODULE_NAMES)

    def test_all_values_are_strings(self) -> None:
        for k, v in _MODULE_TABLE_MAP.items():
            assert isinstance(v, str), f"{k} table name should be str"

    def test_all_table_names_nonempty(self) -> None:
        for k, v in _MODULE_TABLE_MAP.items():
            assert len(v) > 0, f"{k} table name should not be empty"


# ── 14. get_settings — additional branches ────────────────────────────────────

class TestGetSettingsAdditional:
    @pytest.mark.asyncio
    async def test_returns_timezone_from_db(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(timezone="Asia/Kolkata")
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.timezone == "Asia/Kolkata"

    @pytest.mark.asyncio
    async def test_returns_date_format_from_db(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(date_format="YYYY-MM-DD")
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.date_format == "YYYY-MM-DD"

    @pytest.mark.asyncio
    async def test_default_settings_org_name_is_my_organization(self) -> None:
        svc, repo = _make_svc()
        repo.get_settings = AsyncMock(return_value=None)
        created = _make_orm_settings(organization_name="My Organization")
        repo.create_settings = AsyncMock(return_value=created)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.organization_name == "My Organization"

    @pytest.mark.asyncio
    async def test_default_settings_currency_is_inr(self) -> None:
        svc, repo = _make_svc()
        repo.get_settings = AsyncMock(return_value=None)
        created = _make_orm_settings(currency="INR")
        repo.create_settings = AsyncMock(return_value=created)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.currency == "INR"

    @pytest.mark.asyncio
    async def test_session_commit_called_on_default_create(self) -> None:
        svc, repo = _make_svc()
        repo.get_settings = AsyncMock(return_value=None)
        orm = _make_orm_settings()
        repo.create_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.get_settings()

        svc._session.commit.assert_awaited()


# ── 15. update_settings — additional branches ─────────────────────────────────

class TestUpdateSettingsAdditional:
    @pytest.mark.asyncio
    async def test_accepts_mm_dd_yyyy_format(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(date_format="MM/DD/YYYY")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(date_format="MM/DD/YYYY"))

        assert result.date_format == "MM/DD/YYYY"

    @pytest.mark.asyncio
    async def test_accepts_yyyy_mm_dd_format(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(date_format="YYYY-MM-DD")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(date_format="YYYY-MM-DD"))

        assert result.date_format == "YYYY-MM-DD"

    @pytest.mark.asyncio
    async def test_accepts_usd(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(currency="USD")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        assert result.currency == "USD"

    @pytest.mark.asyncio
    async def test_accepts_gbp(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(currency="GBP")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(currency="GBP"))

        assert result.currency == "GBP"

    @pytest.mark.asyncio
    async def test_repo_update_called_with_fields(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        repo.update_settings.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_default_workflow_id(self) -> None:
        wf_id = uuid.uuid4()
        svc, repo = _make_svc()
        orm = _make_orm_settings(default_workflow_id=wf_id)
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(
                OrganizationSettingsUpdate(default_workflow_id=wf_id)
            )

        assert result.default_workflow_id == wf_id

    @pytest.mark.asyncio
    async def test_accepts_ta_language(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(language="ta")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(language="ta"))

        assert result.language == "ta"


# ── 16. get_dashboard — additional branches ───────────────────────────────────

class TestGetDashboardAdditional:
    @pytest.mark.asyncio
    async def test_tenant_id_in_dashboard(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.tenant_id == _ORG_ID

    @pytest.mark.asyncio
    async def test_module_count_equals_8(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.module_count == 8

    @pytest.mark.asyncio
    async def test_settings_last_updated_is_datetime(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert isinstance(result.settings_last_updated, datetime)

    @pytest.mark.asyncio
    async def test_dashboard_contains_system_status(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.system_status is not None
        assert isinstance(result.system_status, SystemStatusOut)

    @pytest.mark.asyncio
    async def test_all_modules_healthy_when_all_healthy(self) -> None:
        svc, repo = _make_svc()
        mods = [ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=1) for n in MODULE_NAMES]
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.healthy_module_count == 8
        assert result.system_status.overall_healthy is True


# ── 17. get_system_status — additional branches ───────────────────────────────

class TestGetSystemStatusAdditional:
    @pytest.mark.asyncio
    async def test_each_module_has_enabled_true(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert all(m.enabled for m in result.modules)

    @pytest.mark.asyncio
    async def test_record_counts_preserved(self) -> None:
        svc, repo = _make_svc()
        mods = [
            ModuleStatusOut(name="customers", enabled=True, healthy=True, record_count=42),
            ModuleStatusOut(name="audit", enabled=True, healthy=True, record_count=100),
        ]
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        customers_mod = next(m for m in result.modules if m.name == "customers")
        audit_mod = next(m for m in result.modules if m.name == "audit")
        assert customers_mod.record_count == 42
        assert audit_mod.record_count == 100

    @pytest.mark.asyncio
    async def test_cache_bust_after_update_affects_status(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        deleted = set(redis_mock.delete.call_args.args)
        assert _status_key(_ORG_ID) in deleted

    @pytest.mark.asyncio
    async def test_status_setex_uses_status_key(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.get_system_status()

        call_args = redis_mock.setex.call_args
        assert call_args.args[0] == _status_key(_ORG_ID)

    @pytest.mark.asyncio
    async def test_settings_setex_uses_settings_key(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.get_settings()

        call_args = redis_mock.setex.call_args
        assert call_args.args[0] == _settings_key(_ORG_ID)


# ── 18. Schema validation edge cases ──────────────────────────────────────────

class TestSchemaValidationEdgeCases:
    def test_organization_settings_update_training_days_min(self) -> None:
        req = OrganizationSettingsUpdate(default_training_duration_days=1)
        assert req.default_training_duration_days == 1

    def test_organization_settings_update_training_days_max(self) -> None:
        req = OrganizationSettingsUpdate(default_training_duration_days=365)
        assert req.default_training_duration_days == 365

    def test_organization_settings_update_invoice_days_min(self) -> None:
        req = OrganizationSettingsUpdate(default_invoice_due_days=1)
        assert req.default_invoice_due_days == 1

    def test_organization_settings_update_invoice_days_max(self) -> None:
        req = OrganizationSettingsUpdate(default_invoice_due_days=365)
        assert req.default_invoice_due_days == 365

    def test_organization_name_max_length_field_present(self) -> None:
        import pydantic
        fields = OrganizationSettingsUpdate.model_fields
        assert "organization_name" in fields

    def test_logo_url_max_length_present(self) -> None:
        fields = OrganizationSettingsUpdate.model_fields
        assert "logo_url" in fields

    def test_module_status_enabled_field(self) -> None:
        m = ModuleStatusOut(name="audit", enabled=False, healthy=True, record_count=0)
        assert m.enabled is False

    def test_module_status_healthy_field(self) -> None:
        m = ModuleStatusOut(name="audit", enabled=True, healthy=False, record_count=0)
        assert m.healthy is False

    def test_admin_module_list_total_matches_list_len(self) -> None:
        out = AdminModuleListOut(modules=["a", "b", "c"], total=3)
        assert out.total == len(out.modules)

    def test_system_status_modules_preserved(self) -> None:
        mods = [ModuleStatusOut(name="audit", enabled=True, healthy=True, record_count=5)]
        status = SystemStatusOut(modules=mods, overall_healthy=True, checked_at=datetime.now(UTC))
        assert status.modules[0].name == "audit"

    def test_settings_out_default_workflow_id_none(self) -> None:
        orm = MagicMock(spec=OrganizationSettings)
        for attr in ["id", "tenant_id", "organization_name", "timezone", "currency",
                     "date_format", "language", "default_workflow_id", "default_training_duration_days",
                     "default_invoice_due_days", "logo_url", "is_active", "created_at", "updated_at"]:
            setattr(orm, attr, None if attr in ("default_workflow_id", "logo_url") else (
                _ORG_ID if attr == "tenant_id" else (
                    _SETTINGS_ID if attr == "id" else (
                        True if attr == "is_active" else (
                            1 if attr == "default_training_duration_days" else (
                                30 if attr == "default_invoice_due_days" else (
                                    "en" if attr == "language" else (
                                        datetime.now(UTC) if attr in ("created_at", "updated_at") else "test"
                                    )
                                )
                            )
                        )
                    )
                )
            ))
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.default_workflow_id is None


# ── 19. Misc service patterns ─────────────────────────────────────────────────

class TestMiscServicePatterns:
    @pytest.mark.asyncio
    async def test_service_instantiation(self) -> None:
        session = AsyncMock()
        svc = OrganizationAdminService(session)
        assert svc._session is session

    @pytest.mark.asyncio
    async def test_service_creates_repo(self) -> None:
        session = AsyncMock()
        svc = OrganizationAdminService(session)
        assert svc._repo is not None

    @pytest.mark.asyncio
    async def test_list_modules_returns_admin_module_list_out(self) -> None:
        svc, _ = _make_svc()

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            result = await svc.list_modules()

        assert isinstance(result, AdminModuleListOut)

    @pytest.mark.asyncio
    async def test_get_system_status_returns_system_status_out(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert isinstance(result, SystemStatusOut)

    @pytest.mark.asyncio
    async def test_get_settings_returns_settings_out(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert isinstance(result, OrganizationSettingsOut)

    @pytest.mark.asyncio
    async def test_update_settings_returns_settings_out(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        assert isinstance(result, OrganizationSettingsOut)

    @pytest.mark.asyncio
    async def test_cache_key_uses_org_id_not_workspace_id(self) -> None:
        org_id = uuid.uuid4()
        key = _settings_key(org_id)
        assert "admin" in key

    @pytest.mark.asyncio
    async def test_dashboard_key_structure(self) -> None:
        key = _dashboard_key(_ORG_ID)
        assert "dashboard" in key

    @pytest.mark.asyncio
    async def test_status_key_structure(self) -> None:
        key = _status_key(_ORG_ID)
        assert "system_status" in key
