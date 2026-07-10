"""Unit tests — Bulk Operations service (part 1): schemas, constants, validation.

Sprint 59. Tests are pure-Python; no DB, no Redis.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from corpmind.modules.bulk_operations.schemas import (
    MAX_BATCH_SIZE,
    MAX_CSV_ROWS,
    OPERATION_STATUSES,
    SUPPORTED_ENTITY_TYPES,
    SUPPORTED_OPERATION_TYPES,
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
from corpmind.modules.bulk_operations.service import (
    _ALLOWED_STATUSES,
    _BATCH_SIZE,
    _CACHE_TTL,
    _ENTITY_TABLES,
    _REQUIRED_COLUMNS,
    _history_cache_key,
    _validate_row,
    BulkOperationService,
)
from corpmind.modules.bulk_operations.events import (
    BulkOperationCompleted,
    BulkOperationFailed,
    BulkOperationStarted,
    CsvValidated,
)

ORG = uuid.uuid4()
WS = uuid.uuid4()
USER = uuid.uuid4()
NOW = datetime.now(UTC)


def _make_op(**kwargs):
    from corpmind.modules.bulk_operations.models import BulkOperation
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=ORG,
        workspace_id=WS,
        operation_type="csv_import",
        entity_type="customers",
        status="completed",
        requested_by=USER,
        total_records=5,
        processed_records=5,
        successful_records=5,
        failed_records=0,
        started_at=NOW,
        completed_at=NOW,
        error_summary=None,
        created_at=NOW,
    )
    defaults.update(kwargs)
    op = BulkOperation()
    for k, v in defaults.items():
        setattr(op, k, v)
    return op


# ── Constants ──────────────────────────────────────────────────────────────────

class TestConstants:
    def test_cache_ttl(self):
        assert _CACHE_TTL == 300

    def test_batch_size(self):
        assert _BATCH_SIZE == 100

    def test_max_batch_size(self):
        assert MAX_BATCH_SIZE == 1000

    def test_max_csv_rows(self):
        assert MAX_CSV_ROWS == 5000

    def test_supported_entity_types(self):
        assert "customers" in SUPPORTED_ENTITY_TYPES
        assert "training_engagements" in SUPPORTED_ENTITY_TYPES
        assert "business_tasks" in SUPPORTED_ENTITY_TYPES
        assert "workflow_templates" in SUPPORTED_ENTITY_TYPES

    def test_supported_operation_types(self):
        assert "csv_import" in SUPPORTED_OPERATION_TYPES
        assert "csv_validate" in SUPPORTED_OPERATION_TYPES
        assert "bulk_archive" in SUPPORTED_OPERATION_TYPES
        assert "bulk_status_update" in SUPPORTED_OPERATION_TYPES
        assert "bulk_assignment" in SUPPORTED_OPERATION_TYPES
        assert "dry_run" in SUPPORTED_OPERATION_TYPES

    def test_operation_statuses(self):
        assert "pending" in OPERATION_STATUSES
        assert "running" in OPERATION_STATUSES
        assert "completed" in OPERATION_STATUSES
        assert "failed" in OPERATION_STATUSES
        assert "cancelled" in OPERATION_STATUSES

    def test_required_columns_customers(self):
        assert "company_name" in _REQUIRED_COLUMNS["customers"]
        assert "display_name" in _REQUIRED_COLUMNS["customers"]

    def test_required_columns_training_engagements(self):
        assert "title" in _REQUIRED_COLUMNS["training_engagements"]
        assert "start_date" in _REQUIRED_COLUMNS["training_engagements"]

    def test_required_columns_business_tasks(self):
        assert "title" in _REQUIRED_COLUMNS["business_tasks"]
        assert "status" in _REQUIRED_COLUMNS["business_tasks"]

    def test_required_columns_workflow_templates(self):
        assert "name" in _REQUIRED_COLUMNS["workflow_templates"]
        assert "trigger_event" in _REQUIRED_COLUMNS["workflow_templates"]

    def test_entity_tables(self):
        assert _ENTITY_TABLES["customers"] == "customers"
        assert _ENTITY_TABLES["training_engagements"] == "training_engagements"
        assert _ENTITY_TABLES["business_tasks"] == "business_tasks"
        assert _ENTITY_TABLES["workflow_templates"] == "workflow_templates"

    def test_allowed_statuses_customers(self):
        assert "active" in _ALLOWED_STATUSES["customers"]
        assert "inactive" in _ALLOWED_STATUSES["customers"]
        assert "prospect" in _ALLOWED_STATUSES["customers"]
        assert "churned" in _ALLOWED_STATUSES["customers"]

    def test_allowed_statuses_business_tasks(self):
        assert "open" in _ALLOWED_STATUSES["business_tasks"]
        assert "in_progress" in _ALLOWED_STATUSES["business_tasks"]
        assert "completed" in _ALLOWED_STATUSES["business_tasks"]
        assert "on_hold" in _ALLOWED_STATUSES["business_tasks"]

    def test_allowed_statuses_training_engagements(self):
        assert "draft" in _ALLOWED_STATUSES["training_engagements"]
        assert "scheduled" in _ALLOWED_STATUSES["training_engagements"]
        assert "in_progress" in _ALLOWED_STATUSES["training_engagements"]
        assert "completed" in _ALLOWED_STATUSES["training_engagements"]
        assert "cancelled" in _ALLOWED_STATUSES["training_engagements"]

    def test_allowed_statuses_workflow_templates(self):
        assert "active" in _ALLOWED_STATUSES["workflow_templates"]
        assert "inactive" in _ALLOWED_STATUSES["workflow_templates"]
        assert "draft" in _ALLOWED_STATUSES["workflow_templates"]

    def test_history_cache_key_format(self):
        key = _history_cache_key(ORG, WS)
        assert key.startswith(f"t:{ORG}:bulk:history:")
        assert str(WS) in key

    def test_history_cache_key_distinct_workspaces(self):
        ws2 = uuid.uuid4()
        assert _history_cache_key(ORG, WS) != _history_cache_key(ORG, ws2)

    def test_history_cache_key_distinct_orgs(self):
        org2 = uuid.uuid4()
        assert _history_cache_key(ORG, WS) != _history_cache_key(org2, WS)


# ── Events ────────────────────────────────────────────────────────────────────

class TestEvents:
    def test_bulk_operation_started_fields(self):
        op_id = uuid.uuid4()
        e = BulkOperationStarted(
            operation_id=op_id, workspace_id=WS, operation_type="csv_import",
            entity_type="customers", requested_by=USER, total_records=10,
        )
        assert e.operation_id == op_id
        assert e.total_records == 10
        assert e.occurred_at is not None

    def test_bulk_operation_completed_fields(self):
        op_id = uuid.uuid4()
        e = BulkOperationCompleted(
            operation_id=op_id, workspace_id=WS, operation_type="bulk_archive",
            entity_type="customers", total_records=5, successful_records=4, failed_records=1,
        )
        assert e.successful_records == 4
        assert e.failed_records == 1

    def test_bulk_operation_failed_fields(self):
        op_id = uuid.uuid4()
        e = BulkOperationFailed(
            operation_id=op_id, workspace_id=WS, operation_type="csv_import",
            entity_type="customers", reason="Unrecoverable validation error",
        )
        assert e.reason == "Unrecoverable validation error"

    def test_csv_validated_fields(self):
        e = CsvValidated(
            workspace_id=WS, entity_type="customers",
            total_rows=10, valid_rows=8, invalid_rows=2, dry_run=True,
        )
        assert e.total_rows == 10
        assert e.valid_rows == 8
        assert e.dry_run is True


# ── Schema Validation ─────────────────────────────────────────────────────────

class TestCsvValidateRequest:
    def test_valid_request(self):
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{"company_name": "Acme", "display_name": "Acme Corp"}],
        )
        assert req.entity_type == "customers"

    def test_invalid_entity_type(self):
        with pytest.raises(Exception):
            CsvValidateRequest(workspace_id=WS, entity_type="invalid", rows=[{"a": 1}])

    def test_empty_rows_rejected(self):
        with pytest.raises(Exception):
            CsvValidateRequest(workspace_id=WS, entity_type="customers", rows=[])

    def test_dry_run_defaults_false(self):
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{"company_name": "X", "display_name": "Y"}],
        )
        assert req.dry_run is False

    def test_dry_run_can_be_true(self):
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{"company_name": "X", "display_name": "Y"}],
            dry_run=True,
        )
        assert req.dry_run is True


class TestCsvImportRequest:
    def test_valid_request(self):
        req = CsvImportRequest(
            workspace_id=WS, entity_type="training_engagements",
            rows=[{"title": "T", "start_date": "2026-01-01"}],
            requested_by=USER,
        )
        assert req.stop_on_error is False

    def test_invalid_entity_type(self):
        with pytest.raises(Exception):
            CsvImportRequest(
                workspace_id=WS, entity_type="bogus",
                rows=[{"a": 1}], requested_by=USER,
            )

    def test_stop_on_error_can_be_true(self):
        req = CsvImportRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{"company_name": "X", "display_name": "Y"}],
            requested_by=USER, stop_on_error=True,
        )
        assert req.stop_on_error is True


class TestBulkArchiveRequest:
    def test_valid(self):
        ids = [uuid.uuid4()]
        req = BulkArchiveRequest(workspace_id=WS, entity_type="customers",
                                 entity_ids=ids, requested_by=USER)
        assert len(req.entity_ids) == 1

    def test_invalid_entity_type(self):
        with pytest.raises(Exception):
            BulkArchiveRequest(workspace_id=WS, entity_type="nope",
                               entity_ids=[uuid.uuid4()], requested_by=USER)

    def test_too_many_ids_rejected(self):
        ids = [uuid.uuid4() for _ in range(1001)]
        with pytest.raises(Exception):
            BulkArchiveRequest(workspace_id=WS, entity_type="customers",
                               entity_ids=ids, requested_by=USER)


class TestBulkAssignRequest:
    def test_valid(self):
        req = BulkAssignRequest(workspace_id=WS, entity_type="business_tasks",
                                entity_ids=[uuid.uuid4()], assignee_id=USER,
                                requested_by=USER)
        assert req.assignee_id == USER

    def test_invalid_entity_type(self):
        with pytest.raises(Exception):
            BulkAssignRequest(workspace_id=WS, entity_type="bogus",
                              entity_ids=[uuid.uuid4()], assignee_id=USER,
                              requested_by=USER)


class TestBulkStatusUpdateRequest:
    def test_valid(self):
        req = BulkStatusUpdateRequest(workspace_id=WS, entity_type="customers",
                                      entity_ids=[uuid.uuid4()], new_status="active",
                                      requested_by=USER)
        assert req.new_status == "active"

    def test_empty_ids_rejected(self):
        with pytest.raises(Exception):
            BulkStatusUpdateRequest(workspace_id=WS, entity_type="customers",
                                    entity_ids=[], new_status="active",
                                    requested_by=USER)


# ── _validate_row ─────────────────────────────────────────────────────────────

class TestValidateRowCustomers:
    def test_valid_row(self):
        result = _validate_row(1, {"company_name": "Acme", "display_name": "A"}, "customers")
        assert result.valid is True
        assert result.errors == []

    def test_missing_company_name(self):
        result = _validate_row(1, {"display_name": "A"}, "customers")
        assert result.valid is False
        assert any(e.field == "company_name" for e in result.errors)

    def test_missing_display_name(self):
        result = _validate_row(1, {"company_name": "X"}, "customers")
        assert result.valid is False
        assert any(e.field == "display_name" for e in result.errors)

    def test_empty_company_name(self):
        result = _validate_row(1, {"company_name": "  ", "display_name": "A"}, "customers")
        assert result.valid is False

    def test_invalid_status(self):
        result = _validate_row(1, {"company_name": "X", "display_name": "Y",
                                   "status": "unknown"}, "customers")
        assert result.valid is False
        assert any(e.field == "status" for e in result.errors)

    def test_valid_status_active(self):
        result = _validate_row(1, {"company_name": "X", "display_name": "Y",
                                   "status": "active"}, "customers")
        assert result.valid is True

    def test_valid_status_churned(self):
        result = _validate_row(1, {"company_name": "X", "display_name": "Y",
                                   "status": "churned"}, "customers")
        assert result.valid is True

    def test_row_number_in_result(self):
        result = _validate_row(7, {"company_name": "X", "display_name": "Y"}, "customers")
        assert result.row == 7

    def test_data_populated_on_valid(self):
        row = {"company_name": "Acme", "display_name": "A"}
        result = _validate_row(1, row, "customers")
        assert result.data == row

    def test_data_empty_on_invalid(self):
        result = _validate_row(1, {}, "customers")
        assert result.data == {}

    def test_multiple_errors_reported(self):
        result = _validate_row(1, {}, "customers")
        assert len(result.errors) >= 2


class TestValidateRowTrainingEngagements:
    def test_valid_row(self):
        result = _validate_row(1, {"title": "T", "start_date": "2026-06-01"},
                               "training_engagements")
        assert result.valid is True

    def test_missing_title(self):
        result = _validate_row(1, {"start_date": "2026-01-01"}, "training_engagements")
        assert result.valid is False
        assert any(e.field == "title" for e in result.errors)

    def test_missing_start_date(self):
        result = _validate_row(1, {"title": "T"}, "training_engagements")
        assert result.valid is False
        assert any(e.field == "start_date" for e in result.errors)

    def test_invalid_start_date_format(self):
        result = _validate_row(1, {"title": "T", "start_date": "not-a-date"},
                               "training_engagements")
        assert result.valid is False
        assert any(e.field == "start_date" for e in result.errors)

    def test_valid_iso_datetime(self):
        result = _validate_row(1, {"title": "T", "start_date": "2026-06-01T09:00:00"},
                               "training_engagements")
        assert result.valid is True

    def test_empty_start_date_allowed(self):
        # empty string = blank field, caught by required check (start_date IS required)
        result = _validate_row(1, {"title": "T", "start_date": ""}, "training_engagements")
        assert result.valid is False


class TestValidateRowBusinessTasks:
    def test_valid_row(self):
        result = _validate_row(1, {"title": "Fix bug", "status": "open"}, "business_tasks")
        assert result.valid is True

    def test_missing_title(self):
        result = _validate_row(1, {"status": "open"}, "business_tasks")
        assert result.valid is False

    def test_invalid_status(self):
        result = _validate_row(1, {"title": "T", "status": "done"}, "business_tasks")
        assert result.valid is False
        assert any(e.field == "status" for e in result.errors)

    def test_valid_status_on_hold(self):
        result = _validate_row(1, {"title": "T", "status": "on_hold"}, "business_tasks")
        assert result.valid is True

    def test_valid_status_cancelled(self):
        result = _validate_row(1, {"title": "T", "status": "cancelled"}, "business_tasks")
        assert result.valid is True


class TestValidateRowWorkflowTemplates:
    def test_valid_row(self):
        result = _validate_row(1, {"name": "Onboard", "trigger_event": "customer.created"},
                               "workflow_templates")
        assert result.valid is True

    def test_missing_name(self):
        result = _validate_row(1, {"trigger_event": "e"}, "workflow_templates")
        assert result.valid is False

    def test_missing_trigger_event(self):
        result = _validate_row(1, {"name": "N"}, "workflow_templates")
        assert result.valid is False

    def test_invalid_status(self):
        result = _validate_row(1, {"name": "N", "trigger_event": "e",
                                   "status": "archived"}, "workflow_templates")
        assert result.valid is False

    def test_valid_status_draft(self):
        result = _validate_row(1, {"name": "N", "trigger_event": "e",
                                   "status": "draft"}, "workflow_templates")
        assert result.valid is True


# ── Schema output models ───────────────────────────────────────────────────────

class TestCsvValidationOut:
    def test_basic_construction(self):
        out = CsvValidationOut(
            entity_type="customers", total_rows=3, valid_rows=2,
            invalid_rows=1, dry_run=False, results=[],
        )
        assert out.total_rows == 3
        assert out.invalid_rows == 1

    def test_dry_run_true(self):
        out = CsvValidationOut(
            entity_type="customers", total_rows=1, valid_rows=1,
            invalid_rows=0, dry_run=True, results=[],
        )
        assert out.dry_run is True


class TestBulkOperationOut:
    def test_model_validate_from_orm(self):
        op = _make_op()
        out = BulkOperationOut.model_validate(op)
        assert out.id == op.id
        assert out.status == "completed"
        assert out.successful_records == 5

    def test_completed_at_nullable(self):
        op = _make_op(completed_at=None)
        out = BulkOperationOut.model_validate(op)
        assert out.completed_at is None

    def test_error_summary_nullable(self):
        op = _make_op(error_summary=None)
        out = BulkOperationOut.model_validate(op)
        assert out.error_summary is None

    def test_error_summary_populated(self):
        op = _make_op(error_summary="Row 1: missing field")
        out = BulkOperationOut.model_validate(op)
        assert "Row 1" in out.error_summary


class TestBulkOperationListOut:
    def test_empty_list(self):
        out = BulkOperationListOut(operations=[], total=0)
        assert out.total == 0
        assert out.operations == []

    def test_with_operations(self):
        op = _make_op()
        out = BulkOperationListOut(
            operations=[BulkOperationOut.model_validate(op)], total=1
        )
        assert out.total == 1


class TestRowValidationError:
    def test_fields(self):
        err = RowValidationError(row=3, field="title", message="title is required")
        assert err.row == 3
        assert err.field == "title"


class TestValidationRowResult:
    def test_valid(self):
        r = ValidationRowResult(row=1, valid=True, data={"a": 1})
        assert r.valid is True
        assert r.errors == []

    def test_invalid(self):
        err = RowValidationError(row=1, field="x", message="x is required")
        r = ValidationRowResult(row=1, valid=False, errors=[err])
        assert r.valid is False
        assert len(r.errors) == 1


# ── Service: validate_csv ─────────────────────────────────────────────────────

class TestValidateCsv:
    def _make_ctx(self):
        ctx = MagicMock()
        ctx.org_id = ORG
        return ctx

    @pytest.mark.asyncio
    async def test_all_valid(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context",
            self._make_ctx,
        )
        session = AsyncMock()
        svc = BulkOperationService(session)
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{"company_name": "A", "display_name": "B"}],
        )
        out = await svc.validate_csv(req)
        assert out.total_rows == 1
        assert out.valid_rows == 1
        assert out.invalid_rows == 0

    @pytest.mark.asyncio
    async def test_some_invalid(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context",
            self._make_ctx,
        )
        session = AsyncMock()
        svc = BulkOperationService(session)
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[
                {"company_name": "A", "display_name": "B"},
                {"display_name": "C"},
            ],
        )
        out = await svc.validate_csv(req)
        assert out.total_rows == 2
        assert out.valid_rows == 1
        assert out.invalid_rows == 1

    @pytest.mark.asyncio
    async def test_dry_run_flag_propagated(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context",
            self._make_ctx,
        )
        session = AsyncMock()
        svc = BulkOperationService(session)
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{"company_name": "A", "display_name": "B"}],
            dry_run=True,
        )
        out = await svc.validate_csv(req)
        assert out.dry_run is True

    @pytest.mark.asyncio
    async def test_entity_type_propagated(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context",
            self._make_ctx,
        )
        session = AsyncMock()
        svc = BulkOperationService(session)
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="business_tasks",
            rows=[{"title": "T", "status": "open"}],
        )
        out = await svc.validate_csv(req)
        assert out.entity_type == "business_tasks"

    @pytest.mark.asyncio
    async def test_results_list_matches_row_count(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context",
            self._make_ctx,
        )
        session = AsyncMock()
        svc = BulkOperationService(session)
        rows = [{"company_name": f"C{i}", "display_name": f"D{i}"} for i in range(5)]
        req = CsvValidateRequest(workspace_id=WS, entity_type="customers", rows=rows)
        out = await svc.validate_csv(req)
        assert len(out.results) == 5

    @pytest.mark.asyncio
    async def test_all_invalid(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context",
            self._make_ctx,
        )
        session = AsyncMock()
        svc = BulkOperationService(session)
        req = CsvValidateRequest(
            workspace_id=WS, entity_type="customers",
            rows=[{}, {}],
        )
        out = await svc.validate_csv(req)
        assert out.valid_rows == 0
        assert out.invalid_rows == 2
