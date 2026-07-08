"""Organization admin REST API — Sprint 54: Organization Administration Center."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.admin.schemas import (
    AdminDashboardOut,
    AdminModuleListOut,
    OrganizationSettingsOut,
    OrganizationSettingsUpdate,
    SystemStatusOut,
)
from corpmind.modules.admin.service import OrganizationAdminService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> OrganizationAdminService:
    return OrganizationAdminService(session)


@router.get(
    "/settings",
    response_model=dict,
    summary="Get organization settings",
)
async def get_settings(
    svc: OrganizationAdminService = Depends(_svc),
) -> dict:
    result = await svc.get_settings()
    return {"data": result}


@router.patch(
    "/settings",
    response_model=dict,
    summary="Update organization settings",
)
async def update_settings(
    body: OrganizationSettingsUpdate,
    svc: OrganizationAdminService = Depends(_svc),
) -> dict:
    result = await svc.update_settings(body)
    return {"data": result}


@router.get(
    "/dashboard",
    response_model=dict,
    summary="Get admin dashboard overview",
)
async def get_dashboard(
    svc: OrganizationAdminService = Depends(_svc),
) -> dict:
    result = await svc.get_dashboard()
    return {"data": result}


@router.get(
    "/modules",
    response_model=dict,
    summary="List available modules",
)
async def list_modules(
    svc: OrganizationAdminService = Depends(_svc),
) -> dict:
    result = await svc.list_modules()
    return {"data": result}


@router.get(
    "/system-status",
    response_model=dict,
    summary="Get system-wide module health and record counts",
)
async def get_system_status(
    svc: OrganizationAdminService = Depends(_svc),
) -> dict:
    result = await svc.get_system_status()
    return {"data": result}
