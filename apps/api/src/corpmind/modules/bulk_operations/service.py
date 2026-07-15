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

# DB column names accepted from CSV per entity (whitelist guards against injection via unknown keys)
_ALLOWED_INSERT_COLUMNS: dict[str, frozenset[str]] = {
    "customers": frozenset({
        "company_name", "display_name", "industry", "website", "email", "phone",
        "address", "city", "state", "country", "postal_code", "company_size",
        "annual_revenue_inr", "status", "health_status", "relationship_owner_id",
        "primary_contact_name", "primary_contact_email", "primary_contact_phone", "notes",
    }),
    "training_engagements": frozenset({
        "customer_id", "program_name", "description", "training_type", "delivery_mode",
        "status", "priority", "planned_start_date", "planned_end_date",
        "actual_start_date", "actual_end_date", "estimated_participants",
        "actual_participants", "assigned_trainer_id", "coordinator_id",
        "location", "meeting_link", "notes",
    }),
    "business_tasks": frozenset({
        "title", "description", "priority", "status", "assignee",
        "assigned_user_id", "due_date", "created_by", "source_type",
    }),
    "workflow_templates": frozenset({
        "name", "description", "category", "is_active",
    }),
}

# CSV field name → DB column name for fields that differ between the two
_CSV_TO_DB_RENAME: dict[str, dict[str, str]] = {
    "customers": {},
    "training_engagements": {
        "title": "program_name",
        "start_date": "planned_start_date",
    },
    "business_tasks": {},
    "workflow_templates": {},
}

# Defaults applied before CSV values; CSV wins on conflict
_INSERT_DEFAULTS: dict[str, dict[str, Any]] = {
    "customers": {"status": "active", "health_status": "healthy"},
    "training_engagements": {
        "training_type": "imported",
        "delivery_mode": "other",
        "status": "planned",
        "priority": "medium",
    },
    "business_tasks": {
        "status": "open",
        "priority": "medium",
        "created_by": "bulk_import",
    },
    "workflow_templates": {
        "category": "imported",
        "is_active": True,
    },
}

# Fixed ordered column list for each entity's INSERT (defines shape of every row written)
_ALL_INSERT_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": (
        "id", "tenant_id", "workspace_id",
        "company_name", "display_name", "industry", "website", "email", "phone",
        "address", "city", "state", "country", "postal_code", "company_size",
        "annual_revenue_inr", "status", "health_status", "relationship_owner_id",
        "primary_contact_name", "primary_contact_email", "primary_contact_phone",
        "notes", "created_at", "updated_at",
    ),
    "training_engagements": (
        "id", "tenant_id", "workspace_id",
        "customer_id", "program_name", "description", "training_type", "delivery_mode",
        "status", "priority", "planned_start_date", "planned_end_date",
        "actual_start_date", "actual_end_date", "estimated_participants",
        "actual_participants", "assigned_trainer_id", "coordinator_id",
        "location", "meeting_link", "notes", "created_at", "updated_at",
    ),
    "business_tasks": (
        "id", "tenant_id", "workspace_id",
        "title", "description", "priority", "status", "assignee",
        "assigned_user_id", "due_date", "created_by", "source_type",
        "created_at", "updated_at",
    ),
    "workflow_templates": (
        "id", "tenant_id", "workspace_id",
        "name", "description", "category", "is_active", "created_by", "created_at",
    ),
}


# ── Entity row construction ───────────────────────────────────────────────────

def _build_entity_values(
    row: dict[str, Any],
    entity_type: str,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    requested_by: uuid.UUID,
    now: datetime,
) -> dict[str, Any]:
    """Map a validated CSV row to a complete DB column dict ready for INSERT."""
    rename = _CSV_TO_DB_RENAME[entity_type]
    allowed = _ALLOWED_INSERT_COLUMNS[entity_type]
    values: dict[str, Any] = {**_INSERT_DEFAULTS[entity_type]}

    for csv_col, val in row.items():
        db_col = rename.get(csv_col, csv_col)
        if db_col in allowed:
            values[db_col] = val

    # workflow_templates: CSV status (active/inactive/draft) → is_active bool;
    # created_by is always the requesting user (UUID, not a string label)
    if entity_type == "workflow_templates":
        if "status" in row:
            values["is_active"] = row["status"] == "active"
        values["created_by"] = str(requested_by)

    # System-generated fields always override anything from CSV
    values["id"] = str(uuid.uuid4())
    values["tenant_id"] = str(tenant_id)
    values["workspace_id"] = str(workspace_id)
    values["created_at"] = now.isoformat()
    if entity_type != "workflow_templates":
        values["updated_at"] = now.isoformat()

    # Fill None for every optional column not present in this row
    for col in _ALL_INSERT_COLUMNS[entity_type]:
        values.setdefault(col, None)

    return {col: values[col] for col in _ALL_INSERT_COLUMNS[entity_type]}


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
        """Validate then synchronously import rows. Creates a BulkOperation record.

        Flow:
          1. Validate every row; collect valid rows for insertion.
          2. INSERT valid rows inside a savepoint so a SQL failure can't corrupt
             the BulkOperation tracking record.
          3. Update BulkOperation with final counters and status.
        """
        ctx = get_tenant_context()
        await self._invalidate_history_cache(ctx.org_id, req.workspace_id)
        now = datetime.now(UTC)

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
            started_at=now,
            created_at=now,
        )
        op = await self._repo.create(op)

        log.info(
            "bulk_import_started",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            entity_type=req.entity_type,
            total_rows=len(req.rows),
        )

        # Phase 1: validate — collect valid rows, accumulate error messages
        validation_errors: list[str] = []
        valid_rows: list[dict[str, Any]] = []
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
                    valid_rows.append(result.data)

        # Phase 2: persist valid rows (skipped when stop_on_error aborted early)
        inserted = 0
        insert_error: str | None = None

        if valid_rows and not (req.stop_on_error and failed > 0):
            try:
                async with self._session.begin_nested():
                    inserted = await self._insert_entity_rows(
                        req.entity_type,
                        valid_rows,
                        ctx.org_id,
                        req.workspace_id,
                        req.requested_by,
                        now,
                    )
            except Exception as exc:
                insert_error = str(exc)[:500]
                log.error(
                    "bulk_import_insert_failed",
                    tenant_id=str(ctx.org_id),
                    operation_id=str(op.id),
                    entity_type=req.entity_type,
                    error=insert_error,
                )

        # Phase 3: compute final counters and update tracking record
        has_insert_error = insert_error is not None
        successful = 0 if has_insert_error else inserted
        # Treat valid rows as failed when the INSERT was rolled back
        total_failed = failed + (len(valid_rows) if has_insert_error else 0)
        processed = failed + len(valid_rows)

        all_error_lines = list(validation_errors[:50])
        if insert_error:
            all_error_lines.append(f"Insert failed: {insert_error}")
        error_summary = "\n".join(all_error_lines) if all_error_lines else None

        final_status = (
            "failed"
            if has_insert_error or (req.stop_on_error and failed > 0)
            else "completed"
        )

        updated = await self._repo.update_fields(
            op.id,
            {
                "status": final_status,
                "processed_records": processed,
                "successful_records": successful,
                "failed_records": total_failed,
                "completed_at": now,
                "error_summary": error_summary,
            },
        )

        log.info(
            "bulk_import_completed",
            tenant_id=str(ctx.org_id),
            operation_id=str(op.id),
            successful=successful,
            failed=total_failed,
        )
        return BulkOperationOut.model_validate(updated)

    async def _insert_entity_rows(
        self,
        entity_type: str,
        rows: list[dict[str, Any]],
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        requested_by: uuid.UUID,
        now: datetime,
    ) -> int:
        """INSERT validated rows into the entity table. Raises on SQL error."""
        table = _ENTITY_TABLES[entity_type]
        cols = _ALL_INSERT_COLUMNS[entity_type]
        col_list = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        insert_sql = text(  # noqa: S608
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
        )

        inserted = 0
        for batch_start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[batch_start : batch_start + _BATCH_SIZE]
            for row in batch:
                params = _build_entity_values(
                    row, entity_type, tenant_id, workspace_id, requested_by, now
                )
                await self._session.execute(insert_sql, params)
                inserted += 1

        return inserted

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
