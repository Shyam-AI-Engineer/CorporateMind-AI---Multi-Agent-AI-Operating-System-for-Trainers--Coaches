"""Organization admin repository — Sprint 54: Organization Administration Center."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.admin.models import OrganizationSettings
from corpmind.modules.admin.schemas import ModuleStatusOut

# Mapping: logical module name → (table_name, tenant_id_column)
# Using raw SQL counts so we never import cross-module models/repos.
_MODULE_TABLE_MAP: dict[str, str] = {
    "customers": "customers",
    "training": "training_engagements",
    "billing": "customer_invoices",
    "payments": "invoice_payments",
    "notifications": "notifications",
    "audit": "audit_logs",
    "workflow": "workflow_runs",
    "team": "workspace_members",
}


class OrganizationAdminRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_settings(self) -> OrganizationSettings | None:
        ctx = get_tenant_context()
        result = await self._session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.tenant_id == ctx.org_id
            )
        )
        return result.scalar_one_or_none()

    async def create_settings(self, record: OrganizationSettings) -> OrganizationSettings:
        self._session.add(record)
        await self._session.flush()
        return record

    async def update_settings(
        self,
        setting_id: uuid.UUID,
        fields: dict[str, object],
    ) -> OrganizationSettings | None:
        ctx = get_tenant_context()
        if not fields:
            return await self.get_settings()

        fields["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(OrganizationSettings)
            .where(
                OrganizationSettings.tenant_id == ctx.org_id,
                OrganizationSettings.id == setting_id,
            )
            .values(**fields)
        )
        await self._session.flush()
        return await self.get_settings()

    async def count_module_records(self, module_name: str) -> int:
        """Count tenant-scoped rows for a module using raw SQL against known table names."""
        ctx = get_tenant_context()
        table = _MODULE_TABLE_MAP.get(module_name)
        if not table:
            return 0
        try:
            result = await self._session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid"),
                {"tid": str(ctx.org_id)},
            )
            row = result.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    async def get_module_statuses(self) -> list[ModuleStatusOut]:
        """Return status for each known module using raw count queries."""
        statuses: list[ModuleStatusOut] = []
        for module_name in _MODULE_TABLE_MAP:
            count = await self.count_module_records(module_name)
            statuses.append(
                ModuleStatusOut(
                    name=module_name,
                    enabled=True,
                    healthy=True,
                    record_count=count,
                )
            )
        return statuses
