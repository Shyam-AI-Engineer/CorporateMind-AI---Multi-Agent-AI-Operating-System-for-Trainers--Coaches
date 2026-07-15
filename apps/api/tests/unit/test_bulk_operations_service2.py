"""Unit tests — Bulk Operations service (part 2): import, archive, assign,
status-update, list, get, and cache logic.

Sprint 59. No DB, no Redis (both mocked).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.bulk_operations.schemas import (
    BulkArchiveRequest,
    BulkAssignRequest,
    BulkOperationOut,
    BulkStatusUpdateRequest,
    CsvImportRequest,
)
from corpmind.modules.bulk_operations.service import BulkOperationService, _history_cache_key

ORG = uuid.uuid4()
WS = uuid.uuid4()
USER = uuid.uuid4()
NOW = datetime.now(UTC)


def _make_orm_op(**kwargs):
    from corpmind.modules.bulk_operations.models import BulkOperation

    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=ORG,
        workspace_id=WS,
        operation_type="csv_import",
        entity_type="customers",
        status="completed",
        requested_by=USER,
        total_records=3,
        processed_records=3,
        successful_records=3,
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


def _make_ctx():
    ctx = MagicMock()
    ctx.org_id = ORG
    return ctx


def _make_svc():
    session = AsyncMock()
    # begin_nested() is synchronous in SQLAlchemy (returns an async context manager);
    # configure the mock to reflect that so `async with session.begin_nested()` works.
    nested = AsyncMock()
    nested.__aexit__ = AsyncMock(return_value=False)  # False = propagate exceptions
    session.begin_nested = MagicMock(return_value=nested)
    return BulkOperationService(session), session


# ── import_csv ────────────────────────────────────────────────────────────────

class TestImportCsv:
    @pytest.mark.asyncio
    async def test_all_valid_rows_returns_completed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(status="running", successful_records=0, failed_records=0)
        updated_op = _make_orm_op(status="completed", successful_records=2, failed_records=0)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},
                    {"company_name": "C", "display_name": "D"},
                ],
                requested_by=USER,
            )
            out = await svc.import_csv(req)

        assert out.status == "completed"
        assert out.successful_records == 2

    @pytest.mark.asyncio
    async def test_invalid_rows_counted_as_failed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(status="running")
        updated_op = _make_orm_op(
            status="completed", successful_records=1, failed_records=1,
            error_summary="Row 2: display_name — display_name is required",
        )

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},
                    {"company_name": "C"},
                ],
                requested_by=USER,
            )
            out = await svc.import_csv(req)

        assert out.failed_records == 1
        assert out.error_summary is not None

    @pytest.mark.asyncio
    async def test_stop_on_error_marks_failed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(status="running")
        updated_op = _make_orm_op(status="failed", successful_records=0, failed_records=1)

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "C"}, {"company_name": "A", "display_name": "B"}],
                requested_by=USER, stop_on_error=True,
            )
            out = await svc.import_csv(req)

        assert out.status == "failed"

    @pytest.mark.asyncio
    async def test_repo_create_called_once(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(status="running")
        updated_op = _make_orm_op(status="completed", successful_records=1)

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        svc._repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_operation_type_is_csv_import(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="csv_import", status="running")
        updated_op = _make_orm_op(operation_type="csv_import", status="completed", successful_records=1)

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            out = await svc.import_csv(req)

        assert out.operation_type == "csv_import"

    @pytest.mark.asyncio
    async def test_error_summary_truncated_to_50_lines(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        # 60 invalid rows → error_summary should have at most 50 lines
        created_op = _make_orm_op(status="running")
        rows = [{"x": i} for i in range(60)]
        # capture the update_fields call to inspect fields
        captured_fields = {}

        async def fake_update(op_id, fields):
            captured_fields.update(fields)
            op = _make_orm_op(
                status=fields["status"],
                successful_records=fields["successful_records"],
                failed_records=fields["failed_records"],
                error_summary=fields.get("error_summary"),
            )
            return op

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.side_effect = fake_update

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=rows, requested_by=USER,
            )
            await svc.import_csv(req)

        if captured_fields.get("error_summary"):
            lines = captured_fields["error_summary"].split("\n")
            assert len(lines) <= 50

    @pytest.mark.asyncio
    async def test_cache_invalidated_on_import(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(status="running")
        updated_op = _make_orm_op(status="completed", successful_records=1)

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_redis = AsyncMock()
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        mock_redis.delete.assert_awaited()


# ── bulk_archive ──────────────────────────────────────────────────────────────

class TestBulkArchive:
    @pytest.mark.asyncio
    async def test_returns_operation_out(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_archive", status="running")
        updated_op = _make_orm_op(operation_type="bulk_archive", status="completed",
                                  successful_records=2, failed_records=0)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 2
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkArchiveRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4(), uuid.uuid4()], requested_by=USER,
            )
            out = await svc.bulk_archive(req)

        assert out.operation_type == "bulk_archive"
        assert out.status == "completed"

    @pytest.mark.asyncio
    async def test_operation_type_is_bulk_archive(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_archive", status="running")
        updated_op = _make_orm_op(operation_type="bulk_archive", status="completed")

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkArchiveRequest(
                workspace_id=WS, entity_type="training_engagements",
                entity_ids=[uuid.uuid4()], requested_by=USER,
            )
            out = await svc.bulk_archive(req)

        assert out.operation_type == "bulk_archive"

    @pytest.mark.asyncio
    async def test_execute_called_with_correct_table(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_archive", status="running")
        updated_op = _make_orm_op(operation_type="bulk_archive", status="completed")

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkArchiveRequest(
                workspace_id=WS, entity_type="business_tasks",
                entity_ids=[uuid.uuid4()], requested_by=USER,
            )
            await svc.bulk_archive(req)

        call_args = session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "business_tasks" in sql_str

    @pytest.mark.asyncio
    async def test_failed_rows_counted_when_rowcount_less(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_archive", status="running")

        captured = {}

        async def fake_update(op_id, fields):
            captured.update(fields)
            return _make_orm_op(
                operation_type="bulk_archive",
                successful_records=fields["successful_records"],
                failed_records=fields["failed_records"],
                status=fields["status"],
            )

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.side_effect = fake_update

        mock_result = MagicMock()
        mock_result.rowcount = 1  # only 1 of 2 found
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkArchiveRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4(), uuid.uuid4()], requested_by=USER,
            )
            await svc.bulk_archive(req)

        assert captured["failed_records"] == 1
        assert captured["successful_records"] == 1

    @pytest.mark.asyncio
    async def test_db_exception_caught_counts_as_failed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_archive", status="running")

        captured = {}

        async def fake_update(op_id, fields):
            captured.update(fields)
            return _make_orm_op(
                operation_type="bulk_archive",
                successful_records=fields["successful_records"],
                failed_records=fields["failed_records"],
                status=fields["status"],
            )

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.side_effect = fake_update

        session.execute = AsyncMock(side_effect=RuntimeError("DB error"))

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkArchiveRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4()], requested_by=USER,
            )
            await svc.bulk_archive(req)

        assert captured["failed_records"] == 1
        assert captured["successful_records"] == 0


# ── bulk_assign ───────────────────────────────────────────────────────────────

class TestBulkAssign:
    @pytest.mark.asyncio
    async def test_valid_entity_type_business_tasks(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_assignment", entity_type="business_tasks")
        updated_op = _make_orm_op(operation_type="bulk_assignment", entity_type="business_tasks",
                                  status="completed", successful_records=1)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkAssignRequest(
                workspace_id=WS, entity_type="business_tasks",
                entity_ids=[uuid.uuid4()], assignee_id=USER, requested_by=USER,
            )
            out = await svc.bulk_assign(req)

        assert out.operation_type == "bulk_assignment"

    @pytest.mark.asyncio
    async def test_invalid_entity_type_raises(self, monkeypatch):
        from corpmind.core.exceptions import ValidationError

        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, _ = _make_svc()
        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkAssignRequest(
                workspace_id=WS, entity_type="workflow_templates",
                entity_ids=[uuid.uuid4()], assignee_id=USER, requested_by=USER,
            )
            with pytest.raises(ValidationError):
                await svc.bulk_assign(req)

    @pytest.mark.asyncio
    async def test_customers_assign_uses_assigned_to(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_assignment", entity_type="customers")
        updated_op = _make_orm_op(operation_type="bulk_assignment", entity_type="customers",
                                  status="completed", successful_records=1)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkAssignRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4()], assignee_id=USER, requested_by=USER,
            )
            await svc.bulk_assign(req)

        call_args = session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "assigned_to" in sql_str

    @pytest.mark.asyncio
    async def test_db_exception_gracefully_handled(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_assignment")
        captured = {}

        async def fake_update(op_id, fields):
            captured.update(fields)
            return _make_orm_op(operation_type="bulk_assignment", **fields)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.side_effect = fake_update
        session.execute = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkAssignRequest(
                workspace_id=WS, entity_type="business_tasks",
                entity_ids=[uuid.uuid4()], assignee_id=USER, requested_by=USER,
            )
            await svc.bulk_assign(req)

        assert captured["failed_records"] == 1


# ── bulk_update_status ────────────────────────────────────────────────────────

class TestBulkUpdateStatus:
    @pytest.mark.asyncio
    async def test_valid_status_update(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_status_update")
        updated_op = _make_orm_op(operation_type="bulk_status_update",
                                  status="completed", successful_records=2)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 2
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkStatusUpdateRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4(), uuid.uuid4()],
                new_status="inactive", requested_by=USER,
            )
            out = await svc.bulk_update_status(req)

        assert out.status == "completed"

    @pytest.mark.asyncio
    async def test_invalid_status_raises(self, monkeypatch):
        from corpmind.core.exceptions import ValidationError

        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, _ = _make_svc()
        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkStatusUpdateRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4()], new_status="deleted", requested_by=USER,
            )
            with pytest.raises(ValidationError):
                await svc.bulk_update_status(req)

    @pytest.mark.asyncio
    async def test_sql_contains_new_status(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_status_update")
        updated_op = _make_orm_op(operation_type="bulk_status_update", status="completed")

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkStatusUpdateRequest(
                workspace_id=WS, entity_type="business_tasks",
                entity_ids=[uuid.uuid4()], new_status="completed", requested_by=USER,
            )
            await svc.bulk_update_status(req)

        params = session.execute.call_args[0][1]
        assert params["new_status"] == "completed"

    @pytest.mark.asyncio
    async def test_db_exception_counts_as_failed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_status_update")
        captured = {}

        async def fake_update(op_id, fields):
            captured.update(fields)
            return _make_orm_op(operation_type="bulk_status_update", **fields)

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.side_effect = fake_update
        session.execute = AsyncMock(side_effect=RuntimeError("connection lost"))

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkStatusUpdateRequest(
                workspace_id=WS, entity_type="customers",
                entity_ids=[uuid.uuid4()], new_status="inactive", requested_by=USER,
            )
            await svc.bulk_update_status(req)

        assert captured["failed_records"] == 1

    @pytest.mark.asyncio
    async def test_operation_type_is_bulk_status_update(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        created_op = _make_orm_op(operation_type="bulk_status_update")
        updated_op = _make_orm_op(operation_type="bulk_status_update", status="completed")

        svc, session = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.create.return_value = created_op
        svc._repo.update_fields.return_value = updated_op

        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute = AsyncMock(return_value=mock_result)

        with patch("corpmind.modules.bulk_operations.service.get_redis") as mr:
            mr.return_value = AsyncMock()
            req = BulkStatusUpdateRequest(
                workspace_id=WS, entity_type="workflow_templates",
                entity_ids=[uuid.uuid4()], new_status="inactive", requested_by=USER,
            )
            out = await svc.bulk_update_status(req)

        assert out.operation_type == "bulk_status_update"


# ── list_operations ───────────────────────────────────────────────────────────

class TestListOperations:
    @pytest.mark.asyncio
    async def test_returns_operations(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        ops = [_make_orm_op(), _make_orm_op()]

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_workspace.return_value = ops

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            out = await svc.list_operations(WS)

        assert out.total == 2
        assert len(out.operations) == 2

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        op = _make_orm_op()
        cached_data = {
            "operations": [BulkOperationOut.model_validate(op).model_dump(mode="json")],
            "total": 1,
        }

        svc, _ = _make_svc()
        svc._repo = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(cached_data)
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            out = await svc.list_operations(WS)

        assert out.total == 1
        svc._repo.find_by_workspace.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_hits_db(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        ops = [_make_orm_op()]

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_workspace.return_value = ops

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            out = await svc.list_operations(WS)

        svc._repo.find_by_workspace.assert_awaited_once()
        assert out.total == 1

    @pytest.mark.asyncio
    async def test_cache_not_used_when_filtered(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        ops = [_make_orm_op()]

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_workspace.return_value = ops

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            out = await svc.list_operations(WS, entity_type="customers")

        # Redis.get should NOT be called for filtered queries
        mock_redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_db(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        ops = [_make_orm_op()]

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_workspace.return_value = ops

        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            out = await svc.list_operations(WS)

        assert out.total == 1

    @pytest.mark.asyncio
    async def test_cache_set_after_db_fetch(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        ops = [_make_orm_op()]

        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_workspace.return_value = ops

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            await svc.list_operations(WS)

        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero_total(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_workspace.return_value = []

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        with patch("corpmind.modules.bulk_operations.service.get_redis", return_value=mock_redis):
            out = await svc.list_operations(WS)

        assert out.total == 0


# ── get_operation ─────────────────────────────────────────────────────────────

class TestGetOperation:
    @pytest.mark.asyncio
    async def test_returns_operation(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        op = _make_orm_op()
        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_id.return_value = op
        out = await svc.get_operation(op.id)
        assert out.id == op.id

    @pytest.mark.asyncio
    async def test_not_found_raises(self, monkeypatch):
        from corpmind.core.exceptions import NotFoundError

        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, _ = _make_svc()
        svc._repo = AsyncMock()
        svc._repo.find_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await svc.get_operation(uuid.uuid4())


# ── repo ──────────────────────────────────────────────────────────────────────

class TestBulkOperationRepo:
    @pytest.mark.asyncio
    async def test_find_by_workspace_applies_entity_filter(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.repo.get_tenant_context", _make_ctx
        )
        from corpmind.modules.bulk_operations.repo import BulkOperationRepo

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = BulkOperationRepo(session)
        rows = await repo.find_by_workspace(WS, entity_type="customers")
        assert rows == []
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_for_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.repo.get_tenant_context", _make_ctx
        )
        from corpmind.modules.bulk_operations.repo import BulkOperationRepo

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = BulkOperationRepo(session)
        result = await repo.find_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_create_adds_to_session(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.repo.get_tenant_context", _make_ctx
        )
        from corpmind.modules.bulk_operations.repo import BulkOperationRepo

        session = AsyncMock()
        op = _make_orm_op()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()

        repo = BulkOperationRepo(session)
        result = await repo.create(op)
        session.add.assert_called_once_with(op)

    @pytest.mark.asyncio
    async def test_update_fields_returns_none_for_unknown(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.repo.get_tenant_context", _make_ctx
        )
        from corpmind.modules.bulk_operations.repo import BulkOperationRepo

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = BulkOperationRepo(session)
        result = await repo.update_fields(uuid.uuid4(), {"status": "cancelled"})
        assert result is None
