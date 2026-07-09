"""Security Center & Access Governance REST API — Sprint 58.

All endpoints are GET-only.  No writes, no mutations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.security.schemas import (
    ApiKeyHealthOut,
    AuditSummaryOut,
    PermissionOverviewOut,
    RoleDistributionOut,
    SecurityAlertsOut,
    SecuritySummaryOut,
)
from corpmind.modules.security.service import SecurityCenterService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> SecurityCenterService:
    return SecurityCenterService(session)


@router.get(
    "/summary",
    response_model=SecuritySummaryOut,
    summary="Aggregate security posture snapshot (cached 5 min)",
)
async def get_security_summary(
    svc: SecurityCenterService = Depends(_svc),
) -> SecuritySummaryOut:
    return await svc.get_security_summary()


@router.get(
    "/roles",
    response_model=RoleDistributionOut,
    summary="Workspace member counts grouped by role (cached 5 min)",
)
async def get_role_distribution(
    svc: SecurityCenterService = Depends(_svc),
) -> RoleDistributionOut:
    return await svc.get_role_distribution()


@router.get(
    "/api-keys",
    response_model=ApiKeyHealthOut,
    summary="API key lifecycle health indicators",
)
async def get_api_key_health(
    svc: SecurityCenterService = Depends(_svc),
) -> ApiKeyHealthOut:
    return await svc.get_api_key_health()


@router.get(
    "/audit",
    response_model=AuditSummaryOut,
    summary="Audit log summary for today with top modules",
)
async def get_audit_summary(
    svc: SecurityCenterService = Depends(_svc),
) -> AuditSummaryOut:
    return await svc.get_audit_summary()


@router.get(
    "/permissions",
    response_model=PermissionOverviewOut,
    summary="Per-workspace role distribution overview",
)
async def get_permission_overview(
    svc: SecurityCenterService = Depends(_svc),
) -> PermissionOverviewOut:
    return await svc.get_permission_overview()


@router.get(
    "/alerts",
    response_model=SecurityAlertsOut,
    summary="Rule-based security alerts (cached 5 min)",
)
async def get_security_alerts(
    svc: SecurityCenterService = Depends(_svc),
) -> SecurityAlertsOut:
    return await svc.get_security_alerts()
