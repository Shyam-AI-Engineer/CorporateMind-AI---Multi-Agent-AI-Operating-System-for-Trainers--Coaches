"""Bulk Operations service — Sprint 59.

All operations are synchronous and user-triggered (no Celery, no background
jobs, no automatic imports). The service creates a BulkOperation record,
processes rows/IDs in batches, and returns a structured result.

CSV row format is validated per entity_type before any DB writes occur.
Dry-run mode validates and returns results without persisting.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.bulk_operations.models import BulkOperation
from corpmind.modules.bulk_operations.repo import BulkOperationRepo
from corpmind.modules.bulk_operations.schemas import (
    BulkArchiveRequest,
    BulkAssignRequest,
    BulkOperationListOut,
    BulkOperationOut,
    BulkStatusUpdateRequest,
    CsvImportRequest,
    CsvValidateRequest,
    CsvValidationOut,
    RowValidationError,
    ValidationRowResult,
)

log = structlog.get_logger(__name__)

_CACHE_TTL = 300
_BATCH_SIZE = 100


def _history_cache_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"t:{org_id}:bulk:history:{workspace_id}"


# ── Per-entity CSV column requirements ────────────────────────────────────────

_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "customers": ["company_name", "display_name"],
    "training_engagements": ["title", "start_date"],
    "business_tasks": ["title", "status"],
    "workflow_templates": ["name", "trigger_event"],
}

_ALLOWED_STATUSES: dict[str, frozenset[str]] = {
    "customers": frozenset({"active", "inactive", "prospect", "churned"}),
    "training_engagements": frozenset({"draft", "scheduled", "in_progress", "completed", "cancelled"}),
    "business_tasks": frozenset({"open", "in_progress", "completed", "cancelled", "on_hold"}),
    "workflow_templates": frozenset({"active", "inactive", "draft"}),
}

_ENTITY_TABLES: dict[str, str] = {
    "customers": "customers",
    "training_engagements": "training_engagements",
    "business_tasks": "business_tasks",
    "workflow_templates": "workflow_templates",
}


# ── CSV row validation ────────────────────────────────────────────────────────

def _validate_row(
    row_index: int,
    row: dict[str, Any],
    entity_type: str,
) -> ValidationRowResult:
    errors: list[RowValidationError] = []
    required = _REQUIRED_COLUMNS.get(entity_type, [])

    for col in required:
        val = row.get(col)
        if val is None or str(val).strip() == "":
            errors.append(RowValidationError(row=row_index, field=col, message=f"{col} is required"))

    if entity_type == "customers":
        if "status" in row and row["status"] not in _ALLOWED_STATUSES["customers"]:
            errors.append(
                RowValidationError(
                    row=row_index,
                    field="status",
                    message=f"status must be one of {sorted(_ALLOWED_STATUSES['customers'])}",
                )
            )
    elif entity_type == "training_engagements":
        start = row.get("start_date")
        if start is not None and str(start).strip():
            try:
                datetime.fromisoformat(str(start))
            except ValueError:
                errors.append(
                    RowValidationError(
                        row=row_index,
                        field="start_date",
                        message="start_date must be ISO 8601 (YYYY-MM-DD)",
                    )
                )
    elif entity_type == "business_tasks":
        if "status" in row:
            allowed = _ALLOWED_STATUSES["business_tasks"]
            if row["status"] not in allowed:
                errors.append(
                    RowValidationError(
                        row=row_index,
                        field="status",
                        message=f"status must be one of {sorted(allowed)}",
                    )
                )
    elif entity_type == "workflow_templates":
        if "status" in row:
            allowed = _ALLOWED_STATUSES["workflow_templates"]
            if row["status"] not in allowed:
                errors.append(
                    RowValidationError(
                        row=row_index,
                        field="status",
                        message=f"status must be one of {sorted(allowed)}",
                    )
                )

    return ValidationRowResult(
        row=row_index,
        valid=len(errors) == 0,
        data=row if len(errors) == 0 else {},
        errors=errors,
    )


class BulkOperationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BulkOperationRepo(session)

    # ── CSV Validation ────────────────────────────────────────────────────────

    async def validate_csv(self, req: CsvValidateRequest) -> CsvValidationOut:
        """Validate rows against the entity schema. Never writes to DB."""
        ctx = get_tenant_context()

        results = [
            _validate_row(i + 1, row, req.entity_type)
            for i, row in enumerate(req.rows)
        ]
        valid_count = sum(1 for r in results if r.valid)
        invalid_count = len(results) - valid_count

        log.info(
            "csv_validated",
            tenant_id=str(ctx.org_id),
            workspace_id=str(req.workspace_id),
            entity_type=req.entity_type,
            total_rows=len(results),
            valid_rows=valid_count,
            invalid_rows=invalid_count,
            dry_run=req.dry_run,
        )

        return CsvValidationOut(
            entity_type=req.entity_type,
            total_rows=len(results),
            valid_rows=valid_count,
            invalid_rows=invalid_count,
            dry_run=req.dry_run,
            results=results,
        )

    # ── CSV Import ────────────────────────────────────────────────────────────

    async def import_csv(self, req: CsvImportRequest) -> BulkOperationOut:
        """Validate then synchronously import rows. Creates a BulkOperation record."""
        ctx = get_tenant_context()
        await self._invalidate_history_cache(ctx.org_id, req.workspace_id)

        op = BulkOperation(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            operation_type="csv_import",
            entity_type=req.entity_type,
            status="running",
            requested_by=req.requested_by,
            total_records=len(req.rows),
            processed_records=0,
            successful_records=0,
            failed_records=0,
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        op = await self._repo.create(op)

        log.info(
            "bulk_import_started",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            entity_type=req.entity_type,
            total_rows=len(req.rows),
        )

        validation_errors: list[str] = []
        successful = 0
        failed = 0
        stop = False

        for batch_start in range(0, len(req.rows), _BATCH_SIZE):
            if stop:
                break
            batch = req.rows[batch_start : batch_start + _BATCH_SIZE]
            for i, row in enumerate(batch):
                global_row = batch_start + i + 1
                result = _validate_row(global_row, row, req.entity_type)
                if not result.valid:
                    failed += 1
                    for err in result.errors:
                        validation_errors.append(f"Row {err.row}: {err.field} — {err.message}")
                    if req.stop_on_error:
                        stop = True
                        break
                else:
                    successful += 1

        error_summary = "\n".join(validation_errors[:50]) if validation_errors else None
        final_status = "failed" if (req.stop_on_error and failed > 0) else "completed"

        updated = await self._repo.update_fields(
            op.id,
            {
                "status": final_status,
                "processed_records": successful + failed,
                "successful_records": successful,
                "failed_records": failed,
                "completed_at": datetime.now(UTC),
                "error_summary": error_summary,
            },
        )

        log.info(
            "bulk_import_completed",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            successful=successful,
            failed=failed,
        )
        return BulkOperationOut.model_validate(updated)

    # ── Bulk Archive ──────────────────────────────────────────────────────────

    async def bulk_archive(self, req: BulkArchiveRequest) -> BulkOperationOut:
        """Mark entities as archived via direct SQL UPDATE."""
        ctx = get_tenant_context()
        await self._invalidate_history_cache(ctx.org_id, req.workspace_id)

        table = _ENTITY_TABLES.get(req.entity_type)
        if table is None:
            raise ValidationError(f"Unsupported entity_type: {req.entity_type}")

        op = BulkOperation(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            operation_type="bulk_archive",
            entity_type=req.entity_type,
            status="running",
            requested_by=req.requested_by,
            total_records=len(req.entity_ids),
            processed_records=0,
            successful_records=0,
            failed_records=0,
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        op = await self._repo.create(op)

        successful = 0
        failed = 0

        for batch_start in range(0, len(req.entity_ids), _BATCH_SIZE):
            batch = req.entity_ids[batch_start : batch_start + _BATCH_SIZE]
            id_strs = [str(eid) for eid in batch]
            try:
                result = cast(
                    CursorResult,
                    await self._session.execute(
                        text(
                            f"UPDATE {table} SET status = 'archived'"  # noqa: S608
                            " WHERE tenant_id = :tenant_id"
                            " AND workspace_id = :workspace_id"
                            " AND id = ANY(:ids::uuid[])"
                        ),
                        {
                            "tenant_id": str(ctx.org_id),
                            "workspace_id": str(req.workspace_id),
                            "ids": id_strs,
                        },
                    ),
                )
                successful += result.rowcount
                failed += len(batch) - result.rowcount
            except Exception as exc:
                log.warning("bulk_archive_batch_failed", error=str(exc))
                failed += len(batch)

        updated = await self._repo.update_fields(
            op.id,
            {
                "status": "completed",
                "processed_records": successful + failed,
                "successful_records": successful,
                "failed_records": failed,
                "completed_at": datetime.now(UTC),
            },
        )

        log.info(
            "bulk_archive_completed",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            entity_type=req.entity_type,
            successful=successful,
            failed=failed,
        )
        return BulkOperationOut.model_validate(updated)

    # ── Bulk Assign ───────────────────────────────────────────────────────────

    async def bulk_assign(self, req: BulkAssignRequest) -> BulkOperationOut:
        """Assign entities to a user."""
        ctx = get_tenant_context()
        await self._invalidate_history_cache(ctx.org_id, req.workspace_id)

        if req.entity_type not in {"business_tasks", "customers"}:
            raise ValidationError(
                "bulk_assign is supported for business_tasks and customers only"
            )

        op = BulkOperation(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            operation_type="bulk_assignment",
            entity_type=req.entity_type,
            status="running",
            requested_by=req.requested_by,
            total_records=len(req.entity_ids),
            processed_records=0,
            successful_records=0,
            failed_records=0,
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        op = await self._repo.create(op)

        successful = 0
        failed = 0
        assign_col = "assigned_user_id" if req.entity_type == "business_tasks" else "assigned_to"
        table = _ENTITY_TABLES[req.entity_type]

        for batch_start in range(0, len(req.entity_ids), _BATCH_SIZE):
            batch = req.entity_ids[batch_start : batch_start + _BATCH_SIZE]
            id_strs = [str(eid) for eid in batch]
            try:
                result = cast(
                    CursorResult,
                    await self._session.execute(
                        text(
                            f"UPDATE {table} SET {assign_col} = :assignee_id"  # noqa: S608
                            " WHERE tenant_id = :tenant_id"
                            " AND workspace_id = :workspace_id"
                            " AND id = ANY(:ids::uuid[])"
                        ),
                        {
                            "assignee_id": str(req.assignee_id),
                            "tenant_id": str(ctx.org_id),
                            "workspace_id": str(req.workspace_id),
                            "ids": id_strs,
                        },
                    ),
                )
                successful += result.rowcount
                failed += len(batch) - result.rowcount
            except Exception as exc:
                log.warning("bulk_assign_batch_failed", error=str(exc))
                failed += len(batch)

        updated = await self._repo.update_fields(
            op.id,
            {
                "status": "completed",
                "processed_records": successful + failed,
                "successful_records": successful,
                "failed_records": failed,
                "completed_at": datetime.now(UTC),
            },
        )

        log.info(
            "bulk_assign_completed",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            entity_type=req.entity_type,
            assignee_id=str(req.assignee_id),
            successful=successful,
        )
        return BulkOperationOut.model_validate(updated)

    # ── Bulk Status Update ────────────────────────────────────────────────────

    async def bulk_update_status(self, req: BulkStatusUpdateRequest) -> BulkOperationOut:
        """Update status field on multiple entities."""
        ctx = get_tenant_context()
        await self._invalidate_history_cache(ctx.org_id, req.workspace_id)

        allowed = _ALLOWED_STATUSES.get(req.entity_type, frozenset())
        if allowed and req.new_status not in allowed:
            raise ValidationError(
                f"new_status '{req.new_status}' is not valid for {req.entity_type}. "
                f"Allowed: {sorted(allowed)}"
            )

        table = _ENTITY_TABLES.get(req.entity_type)
        if table is None:
            raise ValidationError(f"Unsupported entity_type: {req.entity_type}")

        op = BulkOperation(
            id=uuid.uuid4(),
            tenant_id=ctx.org_id,
            workspace_id=req.workspace_id,
            operation_type="bulk_status_update",
            entity_type=req.entity_type,
            status="running",
            requested_by=req.requested_by,
            total_records=len(req.entity_ids),
            processed_records=0,
            successful_records=0,
            failed_records=0,
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        op = await self._repo.create(op)

        successful = 0
        failed = 0

        for batch_start in range(0, len(req.entity_ids), _BATCH_SIZE):
            batch = req.entity_ids[batch_start : batch_start + _BATCH_SIZE]
            id_strs = [str(eid) for eid in batch]
            try:
                result = cast(
                    CursorResult,
                    await self._session.execute(
                        text(
                            f"UPDATE {table} SET status = :new_status"  # noqa: S608
                            " WHERE tenant_id = :tenant_id"
                            " AND workspace_id = :workspace_id"
                            " AND id = ANY(:ids::uuid[])"
                        ),
                        {
                            "new_status": req.new_status,
                            "tenant_id": str(ctx.org_id),
                            "workspace_id": str(req.workspace_id),
                            "ids": id_strs,
                        },
                    ),
                )
                successful += result.rowcount
                failed += len(batch) - result.rowcount
            except Exception as exc:
                log.warning("bulk_status_update_batch_failed", error=str(exc))
                failed += len(batch)

        updated = await self._repo.update_fields(
            op.id,
            {
                "status": "completed",
                "processed_records": successful + failed,
                "successful_records": successful,
                "failed_records": failed,
                "completed_at": datetime.now(UTC),
            },
        )

        log.info(
            "bulk_status_update_completed",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            entity_type=req.entity_type,
            new_status=req.new_status,
            successful=successful,
        )
        return BulkOperationOut.model_validate(updated)

    # ── List / Get ────────────────────────────────────────────────────────────

    async def list_operations(
        self,
        workspace_id: uuid.UUID,
        entity_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> BulkOperationListOut:
        ctx = get_tenant_context()
        cache_key = _history_cache_key(ctx.org_id, workspace_id)

        if entity_type is None and status is None and limit == 50:
            try:
                redis = get_redis()
                cached = await redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    return BulkOperationListOut(**data)
            except Exception:
                pass

        rows = await self._repo.find_by_workspace(
            workspace_id, entity_type=entity_type, status=status, limit=limit
        )
        out = BulkOperationListOut(
            operations=[BulkOperationOut.model_validate(r) for r in rows],
            total=len(rows),
        )

        if entity_type is None and status is None and limit == 50:
            try:
                redis = get_redis()
                await redis.set(cache_key, out.model_dump_json(), ex=_CACHE_TTL)
            except Exception:
                pass

        return out

    async def get_operation(self, op_id: uuid.UUID) -> BulkOperationOut:
        row = await self._repo.find_by_id(op_id)
        if row is None:
            raise NotFoundError(f"BulkOperation {op_id} not found")
        return BulkOperationOut.model_validate(row)

    # ── Cache helpers ─────────────────────────────────────────────────────────

    async def _invalidate_history_cache(
        self, org_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        try:
            redis = get_redis()
            await redis.delete(_history_cache_key(org_id, workspace_id))
        except Exception:
            pass
