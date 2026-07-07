"""Audit module REST API — Sprint 53: Audit Log & Compliance Center.

All routes are read-only (GET).  POST is intentionally absent: audit records
are created internally through AuditLogService.log_event(), never via a
public HTTP endpoint.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.audit.schemas import (
    AuditLogFilters,
    AuditLogListOut,
    AuditLogOut,
    AuditStatisticsOut,
)
from corpmind.modules.audit.service import AuditLogService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> AuditLogService:
    return AuditLogService(session)


@router.get(
    "/events",
    response_model=dict,
    summary="List audit events — paginated, filterable",
)
async def list_events(
    workspace_id: uuid.UUID = Query(...),
    module: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    svc: AuditLogService = Depends(_svc),
) -> dict:
    from datetime import datetime

    filters = AuditLogFilters(
        workspace_id=workspace_id,
        module=module,
        severity=severity,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        date_from=datetime.fromisoformat(date_from) if date_from else None,
        date_to=datetime.fromisoformat(date_to) if date_to else None,
        search=search,
        cursor=cursor,
        limit=limit,
    )
    result = await svc.list_events(filters)
    return {"data": result}


@router.get(
    "/events/{log_id}",
    response_model=dict,
    summary="Fetch a single audit event by id",
)
async def get_event(
    log_id: uuid.UUID,
    svc: AuditLogService = Depends(_svc),
) -> dict:
    result = await svc.get_event(log_id)
    return {"data": result}


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=dict,
    summary="All audit events for a specific entity",
)
async def list_entity_events(
    entity_type: str,
    entity_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    svc: AuditLogService = Depends(_svc),
) -> dict:
    result = await svc.list_entity_events(entity_type, entity_id, workspace_id)
    return {"data": result}


@router.get(
    "/user/{user_id}",
    response_model=dict,
    summary="All audit events for a specific user",
)
async def list_user_events(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    svc: AuditLogService = Depends(_svc),
) -> dict:
    result = await svc.list_user_events(user_id, workspace_id)
    return {"data": result}


@router.get(
    "/module/{module}",
    response_model=dict,
    summary="All recent audit events for a specific module",
)
async def list_module_events(
    module: str,
    workspace_id: uuid.UUID = Query(...),
    svc: AuditLogService = Depends(_svc),
) -> dict:
    result = await svc.list_module_events(module, workspace_id)
    return {"data": result}


@router.get(
    "/statistics",
    response_model=dict,
    summary="Aggregate statistics — counts by severity, module, and top actions",
)
async def get_statistics(
    workspace_id: uuid.UUID = Query(...),
    period_days: int = Query(default=30, ge=1, le=365),
    svc: AuditLogService = Depends(_svc),
) -> dict:
    result = await svc.get_statistics(workspace_id, period_days=period_days)
    return {"data": result}
