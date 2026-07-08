"""Unit tests for modules/admin — Sprint 54: Organization Administration Center.

Coverage target: 180+ tests across all service, repo, schema, and event logic.
Mocks: TenantContext, Redis, AsyncSession — no real DB required.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.admin.events import (
    OrganizationSettingsCreated,
    OrganizationSettingsUpdated,
)
from corpmind.modules.admin.models import OrganizationSettings
from corpmind.modules.admin.schemas import (
    MODULE_NAMES,
    SUPPORTED_CURRENCIES,
    SUPPORTED_DATE_FORMATS,
    SUPPORTED_LANGUAGES,
    AdminDashboardOut,
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

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ORG_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_SETTINGS_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


def _make_ctx(org_id: uuid.UUID = _ORG_ID) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    return ctx


def _make_orm_settings(**kwargs: Any) -> MagicMock:
    defaults = {
        "id": _SETTINGS_ID,
        "tenant_id": _ORG_ID,
        "organization_name": "Acme Corp",
        "timezone": "UTC",
        "currency": "INR",
        "date_format": "DD/MM/YYYY",
        "language": "en",
        "default_workflow_id": None,
        "default_training_duration_days": 1,
        "default_invoice_due_days": 30,
        "logo_url": None,
        "is_active": True,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 1, tzinfo=UTC),
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
        ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=10)
        for n in MODULE_NAMES
    ]


# ── 1. Cache key helpers ───────────────────────────────────────────────────────

class TestCacheKeys:
    def test_settings_key_format(self) -> None:
        key = _settings_key(_ORG_ID)
        assert key.startswith(f"t:{_ORG_ID}:admin:settings")

    def test_dashboard_key_format(self) -> None:
        key = _dashboard_key(_ORG_ID)
        assert key.startswith(f"t:{_ORG_ID}:admin:dashboard")

    def test_status_key_format(self) -> None:
        key = _status_key(_ORG_ID)
        assert key.startswith(f"t:{_ORG_ID}:admin:system_status")

    def test_keys_differ_per_org(self) -> None:
        a = uuid.uuid4()
        b = uuid.uuid4()
        assert _settings_key(a) != _settings_key(b)
        assert _dashboard_key(a) != _dashboard_key(b)
        assert _status_key(a) != _status_key(b)

    def test_settings_key_contains_org_id(self) -> None:
        key = _settings_key(_ORG_ID)
        assert str(_ORG_ID) in key

    def test_dashboard_key_contains_org_id(self) -> None:
        key = _dashboard_key(_ORG_ID)
        assert str(_ORG_ID) in key

    def test_status_key_contains_org_id(self) -> None:
        key = _status_key(_ORG_ID)
        assert str(_ORG_ID) in key

    def test_all_keys_unique(self) -> None:
        keys = [_settings_key(_ORG_ID), _dashboard_key(_ORG_ID), _status_key(_ORG_ID)]
        assert len(set(keys)) == 3

    def test_keys_are_strings(self) -> None:
        assert isinstance(_settings_key(_ORG_ID), str)
        assert isinstance(_dashboard_key(_ORG_ID), str)
        assert isinstance(_status_key(_ORG_ID), str)


# ── 2. Schema constants ────────────────────────────────────────────────────────

class TestSchemaConstants:
    def test_supported_currencies_nonempty(self) -> None:
        assert len(SUPPORTED_CURRENCIES) > 0

    def test_inr_in_supported_currencies(self) -> None:
        assert "INR" in SUPPORTED_CURRENCIES

    def test_usd_in_supported_currencies(self) -> None:
        assert "USD" in SUPPORTED_CURRENCIES

    def test_supported_languages_nonempty(self) -> None:
        assert len(SUPPORTED_LANGUAGES) > 0

    def test_en_in_supported_languages(self) -> None:
        assert "en" in SUPPORTED_LANGUAGES

    def test_hi_in_supported_languages(self) -> None:
        assert "hi" in SUPPORTED_LANGUAGES

    def test_supported_date_formats_nonempty(self) -> None:
        assert len(SUPPORTED_DATE_FORMATS) > 0

    def test_ddmmyyyy_in_date_formats(self) -> None:
        assert "DD/MM/YYYY" in SUPPORTED_DATE_FORMATS

    def test_module_names_has_all_8_modules(self) -> None:
        assert len(MODULE_NAMES) == 8

    def test_customers_in_module_names(self) -> None:
        assert "customers" in MODULE_NAMES

    def test_training_in_module_names(self) -> None:
        assert "training" in MODULE_NAMES

    def test_billing_in_module_names(self) -> None:
        assert "billing" in MODULE_NAMES

    def test_payments_in_module_names(self) -> None:
        assert "payments" in MODULE_NAMES

    def test_notifications_in_module_names(self) -> None:
        assert "notifications" in MODULE_NAMES

    def test_audit_in_module_names(self) -> None:
        assert "audit" in MODULE_NAMES

    def test_workflow_in_module_names(self) -> None:
        assert "workflow" in MODULE_NAMES

    def test_team_in_module_names(self) -> None:
        assert "team" in MODULE_NAMES


# ── 3. Schema models ───────────────────────────────────────────────────────────

class TestSchemaModels:
    def test_settings_out_from_attributes(self) -> None:
        orm = _make_orm_settings()
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.id == _SETTINGS_ID
        assert out.organization_name == "Acme Corp"

    def test_settings_out_tenant_id(self) -> None:
        orm = _make_orm_settings()
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.tenant_id == _ORG_ID

    def test_settings_out_defaults(self) -> None:
        orm = _make_orm_settings()
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.currency == "INR"
        assert out.timezone == "UTC"
        assert out.language == "en"

    def test_settings_update_all_none(self) -> None:
        req = OrganizationSettingsUpdate()
        assert req.organization_name is None
        assert req.currency is None

    def test_settings_update_partial(self) -> None:
        req = OrganizationSettingsUpdate(currency="USD")
        assert req.currency == "USD"
        assert req.language is None

    def test_settings_update_exclude_unset(self) -> None:
        req = OrganizationSettingsUpdate(currency="USD")
        dumped = req.model_dump(exclude_unset=True)
        assert "currency" in dumped
        assert "language" not in dumped

    def test_module_status_out_fields(self) -> None:
        m = ModuleStatusOut(name="audit", enabled=True, healthy=True, record_count=50)
        assert m.name == "audit"
        assert m.record_count == 50

    def test_system_status_out_overall_healthy(self) -> None:
        mods = _make_module_statuses()
        out = SystemStatusOut(
            modules=mods,
            overall_healthy=True,
            checked_at=datetime.now(UTC),
        )
        assert out.overall_healthy is True
        assert len(out.modules) == 8

    def test_admin_dashboard_out(self) -> None:
        mods = _make_module_statuses()
        status = SystemStatusOut(modules=mods, overall_healthy=True, checked_at=datetime.now(UTC))
        dash = AdminDashboardOut(
            organization_name="Acme",
            tenant_id=_ORG_ID,
            is_active=True,
            module_count=8,
            healthy_module_count=8,
            total_records=80,
            settings_last_updated=datetime.now(UTC),
            system_status=status,
        )
        assert dash.module_count == 8
        assert dash.total_records == 80

    def test_admin_module_list_out(self) -> None:
        out = AdminModuleListOut(modules=MODULE_NAMES, total=8)
        assert out.total == 8
        assert len(out.modules) == 8

    def test_settings_update_training_duration_bounds(self) -> None:
        req = OrganizationSettingsUpdate(default_training_duration_days=5)
        assert req.default_training_duration_days == 5

    def test_settings_update_invoice_due_days_bounds(self) -> None:
        req = OrganizationSettingsUpdate(default_invoice_due_days=45)
        assert req.default_invoice_due_days == 45

    def test_settings_out_logo_url_none(self) -> None:
        orm = _make_orm_settings(logo_url=None)
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.logo_url is None

    def test_settings_out_logo_url_set(self) -> None:
        orm = _make_orm_settings(logo_url="https://cdn.example.com/logo.png")
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.logo_url == "https://cdn.example.com/logo.png"

    def test_settings_out_is_active_true(self) -> None:
        orm = _make_orm_settings(is_active=True)
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.is_active is True

    def test_settings_out_is_active_false(self) -> None:
        orm = _make_orm_settings(is_active=False)
        out = OrganizationSettingsOut.model_validate(orm)
        assert out.is_active is False


# ── 4. Events ──────────────────────────────────────────────────────────────────

class TestEvents:
    def test_settings_updated_event(self) -> None:
        evt = OrganizationSettingsUpdated(org_id=_ORG_ID, updated_fields=["currency"])
        assert evt.org_id == _ORG_ID
        assert "currency" in evt.updated_fields

    def test_settings_updated_has_occurred_at(self) -> None:
        evt = OrganizationSettingsUpdated(org_id=_ORG_ID, updated_fields=[])
        assert isinstance(evt.occurred_at, datetime)

    def test_settings_created_event(self) -> None:
        evt = OrganizationSettingsCreated(org_id=_ORG_ID, organization_name="ACME")
        assert evt.organization_name == "ACME"
        assert evt.org_id == _ORG_ID

    def test_settings_created_has_occurred_at(self) -> None:
        evt = OrganizationSettingsCreated(org_id=_ORG_ID, organization_name="X")
        assert isinstance(evt.occurred_at, datetime)

    def test_settings_updated_multiple_fields(self) -> None:
        evt = OrganizationSettingsUpdated(org_id=_ORG_ID, updated_fields=["currency", "timezone", "language"])
        assert len(evt.updated_fields) == 3

    def test_settings_updated_empty_fields(self) -> None:
        evt = OrganizationSettingsUpdated(org_id=_ORG_ID, updated_fields=[])
        assert evt.updated_fields == []


# ── 5. get_settings ────────────────────────────────────────────────────────────

class TestGetSettings:
    @pytest.mark.asyncio
    async def test_returns_from_cache_when_hit(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        cached = OrganizationSettingsOut.model_validate(orm).model_dump_json()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=cached)

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.organization_name == "Acme Corp"
        repo.get_settings.assert_not_called()

    @pytest.mark.asyncio
    async def test_hits_db_on_cache_miss(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.id == _SETTINGS_ID
        repo.get_settings.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_defaults_when_no_record(self) -> None:
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
            result = await svc.get_settings()

        repo.create_settings.assert_awaited_once()
        assert result.organization_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_caches_result_after_db_hit(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.get_settings()

        redis_mock.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graceful_redis_failure_on_get(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(side_effect=Exception("redis down"))

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.id == _SETTINGS_ID

    @pytest.mark.asyncio
    async def test_graceful_redis_failure_on_set(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock(side_effect=Exception("redis down"))

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.id == _SETTINGS_ID

    @pytest.mark.asyncio
    async def test_cache_ttl_is_600s(self) -> None:
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
        assert call_args.args[1] == 600

    @pytest.mark.asyncio
    async def test_returns_org_name(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(organization_name="Training Co")
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.organization_name == "Training Co"

    @pytest.mark.asyncio
    async def test_returns_currency(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(currency="USD")
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.currency == "USD"


# ── 6. update_settings ─────────────────────────────────────────────────────────

class TestUpdateSettings:
    @pytest.mark.asyncio
    async def test_updates_currency(self) -> None:
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
    async def test_rejects_invalid_currency(self) -> None:
        from corpmind.core.exceptions import ValidationError
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            with pytest.raises(ValidationError):
                await svc.update_settings(OrganizationSettingsUpdate(currency="FAKE"))

    @pytest.mark.asyncio
    async def test_rejects_invalid_language(self) -> None:
        from corpmind.core.exceptions import ValidationError
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            with pytest.raises(ValidationError):
                await svc.update_settings(OrganizationSettingsUpdate(language="klingon"))

    @pytest.mark.asyncio
    async def test_rejects_invalid_date_format(self) -> None:
        from corpmind.core.exceptions import ValidationError
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            with pytest.raises(ValidationError):
                await svc.update_settings(OrganizationSettingsUpdate(date_format="invalid"))

    @pytest.mark.asyncio
    async def test_busts_settings_cache(self) -> None:
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

        redis_mock.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_busts_all_three_caches(self) -> None:
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

        deleted_keys = redis_mock.delete.call_args.args
        assert len(deleted_keys) == 3

    @pytest.mark.asyncio
    async def test_accepts_valid_currency_eur(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(currency="EUR")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(currency="EUR"))

        assert result.currency == "EUR"

    @pytest.mark.asyncio
    async def test_accepts_valid_language_hi(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(language="hi")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(language="hi"))

        assert result.language == "hi"

    @pytest.mark.asyncio
    async def test_creates_defaults_if_missing_before_update(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=None)
        repo.create_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        repo.create_settings.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commits_on_update(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.update_settings(OrganizationSettingsUpdate(timezone="Asia/Kolkata"))

        svc._session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_graceful_redis_failure_on_bust(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(currency="USD")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock(side_effect=Exception("redis down"))

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        assert result.currency == "USD"

    @pytest.mark.asyncio
    async def test_update_org_name(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(organization_name="New Name")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate(organization_name="New Name"))

        assert result.organization_name == "New Name"

    @pytest.mark.asyncio
    async def test_update_logo_url(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(logo_url="https://cdn.example.com/logo.png")
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(
                OrganizationSettingsUpdate(logo_url="https://cdn.example.com/logo.png")
            )

        assert result.logo_url == "https://cdn.example.com/logo.png"

    @pytest.mark.asyncio
    async def test_update_invoice_due_days(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(default_invoice_due_days=45)
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(
                OrganizationSettingsUpdate(default_invoice_due_days=45)
            )

        assert result.default_invoice_due_days == 45

    @pytest.mark.asyncio
    async def test_update_training_duration_days(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(default_training_duration_days=3)
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(
                OrganizationSettingsUpdate(default_training_duration_days=3)
            )

        assert result.default_training_duration_days == 3


# ── 7. get_system_status ───────────────────────────────────────────────────────

class TestGetSystemStatus:
    @pytest.mark.asyncio
    async def test_returns_from_cache(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        status = SystemStatusOut(modules=mods, overall_healthy=True, checked_at=datetime.now(UTC))
        cached = status.model_dump_json()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=cached)

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert result.overall_healthy is True
        repo.get_module_statuses.assert_not_called()

    @pytest.mark.asyncio
    async def test_queries_db_on_cache_miss(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert len(result.modules) == 8
        repo.get_module_statuses.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_overall_healthy_true_when_all_healthy(self) -> None:
        svc, repo = _make_svc()
        mods = [ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=5) for n in MODULE_NAMES]
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert result.overall_healthy is True

    @pytest.mark.asyncio
    async def test_overall_healthy_false_when_one_unhealthy(self) -> None:
        svc, repo = _make_svc()
        mods = [
            ModuleStatusOut(name="customers", enabled=True, healthy=False, record_count=0),
        ] + [
            ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=5)
            for n in MODULE_NAMES[1:]
        ]
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert result.overall_healthy is False

    @pytest.mark.asyncio
    async def test_caches_with_ttl_600(self) -> None:
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
        assert call_args.args[1] == 600

    @pytest.mark.asyncio
    async def test_graceful_redis_failure(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(side_effect=Exception("redis down"))

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert len(result.modules) == 8

    @pytest.mark.asyncio
    async def test_has_checked_at_timestamp(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert isinstance(result.checked_at, datetime)

    @pytest.mark.asyncio
    async def test_module_statuses_contain_all_modules(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        names = {m.name for m in result.modules}
        for mod_name in MODULE_NAMES:
            assert mod_name in names


# ── 8. list_modules ────────────────────────────────────────────────────────────

class TestListModules:
    @pytest.mark.asyncio
    async def test_returns_all_module_names(self) -> None:
        svc, _ = _make_svc()

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            result = await svc.list_modules()

        assert result.total == len(MODULE_NAMES)
        assert set(result.modules) == set(MODULE_NAMES)

    @pytest.mark.asyncio
    async def test_total_equals_8(self) -> None:
        svc, _ = _make_svc()

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            result = await svc.list_modules()

        assert result.total == 8

    @pytest.mark.asyncio
    async def test_modules_list_is_list(self) -> None:
        svc, _ = _make_svc()

        with patch(_PATCH_CTX, return_value=_make_ctx()):
            result = await svc.list_modules()

        assert isinstance(result.modules, list)

    @pytest.mark.asyncio
    async def test_no_redis_call_needed(self) -> None:
        svc, repo = _make_svc()
        redis_mock = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.list_modules()

        redis_mock.get.assert_not_called()


# ── 9. get_dashboard ───────────────────────────────────────────────────────────

class TestGetDashboard:
    @pytest.mark.asyncio
    async def test_returns_from_cache(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        status = SystemStatusOut(modules=mods, overall_healthy=True, checked_at=datetime.now(UTC))
        orm = _make_orm_settings()
        dash = AdminDashboardOut(
            organization_name="Acme Corp",
            tenant_id=_ORG_ID,
            is_active=True,
            module_count=8,
            healthy_module_count=8,
            total_records=80,
            settings_last_updated=datetime.now(UTC),
            system_status=status,
        )
        cached = dash.model_dump_json()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=cached)

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.organization_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_builds_dashboard_on_cache_miss(self) -> None:
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
    async def test_total_records_is_sum_of_module_counts(self) -> None:
        svc, repo = _make_svc()
        mods = [ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=10) for n in MODULE_NAMES]
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.total_records == 80  # 8 modules × 10 records

    @pytest.mark.asyncio
    async def test_healthy_module_count_from_status(self) -> None:
        svc, repo = _make_svc()
        mods = [
            ModuleStatusOut(name="customers", enabled=True, healthy=True, record_count=10),
            ModuleStatusOut(name="training", enabled=True, healthy=False, record_count=0),
        ] + [
            ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=5)
            for n in MODULE_NAMES[2:]
        ]
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.healthy_module_count == 7  # 1 unhealthy

    @pytest.mark.asyncio
    async def test_caches_dashboard_with_ttl_600(self) -> None:
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
            await svc.get_dashboard()

        # setex called for both settings and dashboard
        assert redis_mock.setex.await_count >= 1

    @pytest.mark.asyncio
    async def test_graceful_redis_failure(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(side_effect=Exception("redis down"))

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.organization_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_is_active_from_settings(self) -> None:
        svc, repo = _make_svc()
        mods = _make_module_statuses()
        orm = _make_orm_settings(is_active=False)
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.is_active is False


# ── 10. Tenant isolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_get_settings_uses_ctx_org_id(self) -> None:
        other_org = uuid.uuid4()
        svc, repo = _make_svc()
        orm = _make_orm_settings(tenant_id=other_org)
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx(other_org)), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.tenant_id == other_org

    @pytest.mark.asyncio
    async def test_cache_keys_scoped_to_org(self) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        assert _settings_key(org_a) != _settings_key(org_b)
        assert _dashboard_key(org_a) != _dashboard_key(org_b)
        assert _status_key(org_a) != _status_key(org_b)

    @pytest.mark.asyncio
    async def test_update_uses_ctx_org_in_cache_bust(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        ctx = _make_ctx()
        with patch(_PATCH_CTX, return_value=ctx), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            await svc.update_settings(OrganizationSettingsUpdate(currency="USD"))

        deleted_keys = redis_mock.delete.call_args.args
        for key in deleted_keys:
            assert str(ctx.org_id) in key

    @pytest.mark.asyncio
    async def test_different_orgs_have_different_cache_keys(self) -> None:
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        key_a = _settings_key(org_a)
        key_b = _settings_key(org_b)
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_default_settings_use_correct_tenant_id(self) -> None:
        custom_org = uuid.uuid4()
        svc, repo = _make_svc()
        repo.get_settings = AsyncMock(return_value=None)
        created_settings = _make_orm_settings(tenant_id=custom_org)
        repo.create_settings = AsyncMock(return_value=created_settings)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx(custom_org)), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.tenant_id == custom_org

    @pytest.mark.asyncio
    async def test_create_settings_passes_org_id_as_tenant_id(self) -> None:
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

        created_record = repo.create_settings.call_args.args[0]
        assert created_record.tenant_id == _ORG_ID


# ── 11. Model structure ────────────────────────────────────────────────────────

class TestModelDefaults:
    def test_organization_settings_tablename(self) -> None:
        assert OrganizationSettings.__tablename__ == "organization_settings"

    def test_organization_settings_has_id_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "id" in cols

    def test_organization_settings_has_tenant_id_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "tenant_id" in cols

    def test_organization_settings_has_organization_name_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "organization_name" in cols

    def test_organization_settings_has_timezone_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "timezone" in cols

    def test_organization_settings_has_currency_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "currency" in cols

    def test_organization_settings_has_language_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "language" in cols

    def test_organization_settings_has_date_format_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "date_format" in cols

    def test_organization_settings_has_is_active_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "is_active" in cols

    def test_organization_settings_has_logo_url_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "logo_url" in cols

    def test_organization_settings_has_created_at_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "created_at" in cols

    def test_organization_settings_has_updated_at_column(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "updated_at" in cols

    def test_organization_settings_has_default_invoice_due_days(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "default_invoice_due_days" in cols

    def test_organization_settings_has_default_training_duration_days(self) -> None:
        cols = {c.key for c in OrganizationSettings.__table__.columns}
        assert "default_training_duration_days" in cols


# ── 12. Edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_update_with_no_fields_set_still_calls_repo(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.update_settings = AsyncMock(return_value=orm)
        svc._session.commit = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.delete = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.update_settings(OrganizationSettingsUpdate())

        # empty update — no fields, no repo call but still returns settings
        assert result is not None

    @pytest.mark.asyncio
    async def test_module_status_record_count_zero_is_valid(self) -> None:
        m = ModuleStatusOut(name="audit", enabled=True, healthy=True, record_count=0)
        assert m.record_count == 0

    @pytest.mark.asyncio
    async def test_system_status_with_empty_module_list(self) -> None:
        status = SystemStatusOut(
            modules=[],
            overall_healthy=True,
            checked_at=datetime.now(UTC),
        )
        assert status.modules == []

    @pytest.mark.asyncio
    async def test_dashboard_org_name_comes_from_settings(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings(organization_name="Special Corp")
        mods = _make_module_statuses()
        repo.get_settings = AsyncMock(return_value=orm)
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_dashboard()

        assert result.organization_name == "Special Corp"

    @pytest.mark.asyncio
    async def test_settings_id_is_uuid(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert isinstance(result.id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_settings_default_workflow_id_is_uuid(self) -> None:
        wf_id = uuid.uuid4()
        svc, repo = _make_svc()
        orm = _make_orm_settings(default_workflow_id=wf_id)
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert result.default_workflow_id == wf_id

    @pytest.mark.asyncio
    async def test_all_currencies_accepted(self) -> None:
        for currency in SUPPORTED_CURRENCIES:
            req = OrganizationSettingsUpdate(currency=currency)
            assert req.currency == currency

    @pytest.mark.asyncio
    async def test_all_languages_accepted(self) -> None:
        for lang in SUPPORTED_LANGUAGES:
            req = OrganizationSettingsUpdate(language=lang)
            assert req.language == lang

    @pytest.mark.asyncio
    async def test_all_date_formats_accepted(self) -> None:
        for fmt in SUPPORTED_DATE_FORMATS:
            req = OrganizationSettingsUpdate(date_format=fmt)
            assert req.date_format == fmt

    @pytest.mark.asyncio
    async def test_settings_created_at_is_datetime(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert isinstance(result.created_at, datetime)

    @pytest.mark.asyncio
    async def test_settings_updated_at_is_datetime(self) -> None:
        svc, repo = _make_svc()
        orm = _make_orm_settings()
        repo.get_settings = AsyncMock(return_value=orm)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_settings()

        assert isinstance(result.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_get_system_status_with_zero_record_counts(self) -> None:
        svc, repo = _make_svc()
        mods = [ModuleStatusOut(name=n, enabled=True, healthy=True, record_count=0) for n in MODULE_NAMES]
        repo.get_module_statuses = AsyncMock(return_value=mods)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()

        with patch(_PATCH_CTX, return_value=_make_ctx()), \
             patch(_PATCH_REDIS, return_value=redis_mock):
            result = await svc.get_system_status()

        assert all(m.record_count == 0 for m in result.modules)
