"""Organization admin service — Sprint 54: Organization Administration Center."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.admin.events import OrganizationSettingsCreated, OrganizationSettingsUpdated
from corpmind.modules.admin.models import OrganizationSettings
from corpmind.modules.admin.repo import OrganizationAdminRepo
from corpmind.modules.admin.schemas import (
    SUPPORTED_CURRENCIES,
    SUPPORTED_DATE_FORMATS,
    SUPPORTED_LANGUAGES,
    MODULE_NAMES,
    AdminDashboardOut,
    AdminModuleListOut,
    OrganizationSettingsOut,
    OrganizationSettingsUpdate,
    SystemStatusOut,
)

log = structlog.get_logger(__name__)

# ── Cache config ───────────────────────────────────────────────────────────────

_SETTINGS_TTL = 600
_DASHBOARD_TTL = 600
_STATUS_TTL = 600


def _settings_key(org_id: uuid.UUID) -> str:
    return f"t:{org_id}:admin:settings"


def _dashboard_key(org_id: uuid.UUID) -> str:
    return f"t:{org_id}:admin:dashboard"


def _status_key(org_id: uuid.UUID) -> str:
    return f"t:{org_id}:admin:system_status"


# ── Service ────────────────────────────────────────────────────────────────────

class OrganizationAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = OrganizationAdminRepo(session)

    async def get_settings(self) -> OrganizationSettingsOut:
        ctx = get_tenant_context()
        cache_key = _settings_key(ctx.org_id)

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return OrganizationSettingsOut.model_validate_json(cached)
        except Exception:
            pass

        record = await self._repo.get_settings()
        if record is None:
            record = await self._ensure_default_settings(ctx.org_id)

        out = OrganizationSettingsOut.model_validate(record)

        try:
            redis = get_redis()
            await redis.setex(cache_key, _SETTINGS_TTL, out.model_dump_json())
        except Exception:
            pass

        return out

    async def update_settings(self, req: OrganizationSettingsUpdate) -> OrganizationSettingsOut:
        ctx = get_tenant_context()

        # Validate fields
        if req.currency is not None and req.currency not in SUPPORTED_CURRENCIES:
            raise ValidationError(f"Unsupported currency '{req.currency}'. Supported: {sorted(SUPPORTED_CURRENCIES)}")
        if req.language is not None and req.language not in SUPPORTED_LANGUAGES:
            raise ValidationError(f"Unsupported language '{req.language}'. Supported: {sorted(SUPPORTED_LANGUAGES)}")
        if req.date_format is not None and req.date_format not in SUPPORTED_DATE_FORMATS:
            raise ValidationError(f"Unsupported date_format '{req.date_format}'. Supported: {sorted(SUPPORTED_DATE_FORMATS)}")

        record = await self._repo.get_settings()
        if record is None:
            record = await self._ensure_default_settings(ctx.org_id)

        fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
        updated_field_names = list(fields.keys())

        updated = await self._repo.update_settings(record.id, fields)
        await self._session.commit()

        # Bust all caches for this org
        try:
            redis = get_redis()
            await redis.delete(
                _settings_key(ctx.org_id),
                _dashboard_key(ctx.org_id),
                _status_key(ctx.org_id),
            )
        except Exception:
            pass

        log.info(
            "admin.settings_updated",
            tenant_id=str(ctx.org_id),
            updated_fields=updated_field_names,
        )

        event = OrganizationSettingsUpdated(
            org_id=ctx.org_id,
            updated_fields=updated_field_names,
        )
        log.debug("admin.event_fired", evt=event.__class__.__name__, org_id=str(event.org_id))

        if updated is None:
            raise NotFoundError("Organization settings not found after update.")
        return OrganizationSettingsOut.model_validate(updated)

    async def get_dashboard(self) -> AdminDashboardOut:
        ctx = get_tenant_context()
        cache_key = _dashboard_key(ctx.org_id)

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return AdminDashboardOut.model_validate_json(cached)
        except Exception:
            pass

        settings = await self.get_settings()
        system_status = await self.get_system_status()

        healthy_count = sum(1 for m in system_status.modules if m.healthy)
        total_records = sum(m.record_count for m in system_status.modules)

        out = AdminDashboardOut(
            organization_name=settings.organization_name,
            tenant_id=settings.tenant_id,
            is_active=settings.is_active,
            module_count=len(system_status.modules),
            healthy_module_count=healthy_count,
            total_records=total_records,
            settings_last_updated=settings.updated_at,
            system_status=system_status,
        )

        try:
            redis = get_redis()
            await redis.setex(cache_key, _DASHBOARD_TTL, out.model_dump_json())
        except Exception:
            pass

        return out

    async def list_modules(self) -> AdminModuleListOut:
        return AdminModuleListOut(modules=MODULE_NAMES, total=len(MODULE_NAMES))

    async def get_system_status(self) -> SystemStatusOut:
        ctx = get_tenant_context()
        cache_key = _status_key(ctx.org_id)

        try:
            redis = get_redis()
            cached = await redis.get(cache_key)
            if cached:
                return SystemStatusOut.model_validate_json(cached)
        except Exception:
            pass

        module_statuses = await self._repo.get_module_statuses()
        overall_healthy = all(m.healthy for m in module_statuses)

        out = SystemStatusOut(
            modules=module_statuses,
            overall_healthy=overall_healthy,
            checked_at=datetime.now(UTC),
        )

        try:
            redis = get_redis()
            await redis.setex(cache_key, _STATUS_TTL, out.model_dump_json())
        except Exception:
            pass

        return out

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _ensure_default_settings(self, org_id: uuid.UUID) -> OrganizationSettings:
        """Create default settings row if none exists yet (idempotent)."""
        record = OrganizationSettings(
            id=uuid.uuid4(),
            tenant_id=org_id,
            organization_name="My Organization",
            timezone="UTC",
            currency="INR",
            date_format="DD/MM/YYYY",
            language="en",
            default_workflow_id=None,
            default_training_duration_days=1,
            default_invoice_due_days=30,
            logo_url=None,
            is_active=True,
        )
        created = await self._repo.create_settings(record)
        await self._session.commit()

        log.info("admin.settings_created", tenant_id=str(org_id))
        event = OrganizationSettingsCreated(
            org_id=org_id,
            organization_name=record.organization_name,
        )
        log.debug("admin.event_fired", evt=event.__class__.__name__)
        return created
