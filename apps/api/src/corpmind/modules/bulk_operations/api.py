"""Bulk Operations REST API — Sprint 59."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_session
from corpmind.modules.bulk_operations.schemas import (
    BulkArchiveRequest,
    BulkAssignRequest,
    BulkOperationListOut,
    BulkOperationOut,
    BulkStatusUpdateRequest,
    CsvImportRequest,
    CsvValidateRequest,
    CsvValidationOut,
)
from corpmind.modules.bulk_operations.service import BulkOperationService

router = APIRouter()


def _svc(session: AsyncSession = Depends(get_session)) -> BulkOperationService:
    return BulkOperationService(session)


@router.post(
    "/validate",
    response_model=CsvValidationOut,
    status_code=200,
    summary="Validate CSV rows against entity schema (never writes to DB)",
)
async def validate_csv(
    body: CsvValidateRequest,
    svc: BulkOperationService = Depends(_svc),
) -> CsvValidationOut:
    return await svc.validate_csv(body)


@router.post(
    "/import",
    response_model=BulkOperationOut,
    status_code=201,
    summary="Validate and synchronously import CSV rows; creates a BulkOperation record",
)
async def import_csv(
    body: CsvImportRequest,
    svc: BulkOperationService = Depends(_svc),
) -> BulkOperationOut:
    return await svc.import_csv(body)


@router.post(
    "/archive",
    response_model=BulkOperationOut,
    status_code=201,
    summary="Bulk archive entities by ID list",
)
async def bulk_archive(
    body: BulkArchiveRequest,
    svc: BulkOperationService = Depends(_svc),
) -> BulkOperationOut:
    return await svc.bulk_archive(body)


@router.post(
    "/assign",
    response_model=BulkOperationOut,
    status_code=201,
    summary="Bulk assign entities to a user",
)
async def bulk_assign(
    body: BulkAssignRequest,
    svc: BulkOperationService = Depends(_svc),
) -> BulkOperationOut:
    return await svc.bulk_assign(body)


@router.post(
    "/status",
    response_model=BulkOperationOut,
    status_code=201,
    summary="Bulk update status on entities",
)
async def bulk_update_status(
    body: BulkStatusUpdateRequest,
    svc: BulkOperationService = Depends(_svc),
) -> BulkOperationOut:
    return await svc.bulk_update_status(body)


@router.get(
    "",
    response_model=BulkOperationListOut,
    summary="List bulk operations for a workspace",
)
async def list_operations(
    workspace_id: uuid.UUID = Query(...),
    entity_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    svc: BulkOperationService = Depends(_svc),
) -> BulkOperationListOut:
    return await svc.list_operations(
        workspace_id, entity_type=entity_type, status=status, limit=limit
    )


@router.get(
    "/{op_id}",
    response_model=BulkOperationOut,
    summary="Get a single bulk operation record",
)
async def get_operation(
    op_id: uuid.UUID,
    svc: BulkOperationService = Depends(_svc),
) -> BulkOperationOut:
    return await svc.get_operation(op_id)
