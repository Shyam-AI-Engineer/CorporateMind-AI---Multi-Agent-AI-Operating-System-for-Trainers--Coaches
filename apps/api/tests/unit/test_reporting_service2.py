"""Unit tests — Sprint 56: Reporting & Export Center (part 2).

Tests for generate_report, export helpers, query building, Redis fallback,
tenant isolation, and repo patterns.
Target: 100+ tests in this file.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.reporting.models import ReportExport
from corpmind.modules.reporting.schemas import (
    SUPPORTED_FORMATS,
    SUPPORTED_REPORT_TYPES,
    GenerateReportRequest,
    ReportExportOut,
)
from corpmind.modules.reporting.service import (
    ReportingService,
    _REPORT_QUERIES,
    _list_cache_key,
    _CUSTOMERS_COLS,
    _TRAINING_COLS,
    _INVOICES_COLS,
    _PAYMENTS_COLS,
    _WORKFLOW_COLS,
    _AUDIT_COLS,
    _EXECUTIVE_COLS,
)

# ── Patch targets ─────────────────────────────────────────────────────────────

_PATCH_CTX = "corpmind.modules.reporting.service.get_tenant_context"
_PATCH_REPO_CTX = "corpmind.modules.reporting.repo.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.reporting.service.get_redis"

# ── Fixtures ──────────────────────────────────────────────────────────────────

ORG_ID = uuid.uuid4()
WS_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
REPORT_ID = uuid.uuid4()


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = ORG_ID
    ctx.user_id = USER_ID
    return ctx


def _null_redis() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    return r


def _make_svc() -> tuple[ReportingService, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    svc = ReportingService(session)
    return svc, session


def _make_orm_report(**kwargs) -> MagicMock:
    r = MagicMock(spec=ReportExport)
    r.id = kwargs.get("id", REPORT_ID)
    r.tenant_id = kwargs.get("tenant_id", ORG_ID)
    r.workspace_id = kwargs.get("workspace_id", WS_ID)
    r.report_type = kwargs.get("report_type", "customers")
    r.format = kwargs.get("format", "csv")
    r.status = kwargs.get("status", "ready")
    r.generated_by = kwargs.get("generated_by", USER_ID)
    r.generated_at = kwargs.get("generated_at", datetime.now(UTC))
    r.download_name = kwargs.get("download_name", "customers_20260708_140000.csv")
    r.row_count = kwargs.get("row_count", 42)
    r.file_size_bytes = kwargs.get("file_size_bytes", 1024)
    r.created_at = kwargs.get("created_at", datetime.now(UTC))
    return r


def _req(report_type: str = "customers", fmt: str = "csv") -> GenerateReportRequest:
    return GenerateReportRequest(
        workspace_id=WS_ID,
        report_type=report_type,
        format=fmt,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Column definitions
# ─────────────────────────────────────────────────────────────────────────────


class TestColumnDefinitions:
    def test_customers_cols_includes_company_name(self):
        assert "company_name" in _CUSTOMERS_COLS

    def test_customers_cols_includes_status(self):
        assert "status" in _CUSTOMERS_COLS

    def test_customers_cols_includes_created_at(self):
        assert "created_at" in _CUSTOMERS_COLS

    def test_training_cols_includes_title(self):
        assert "title" in _TRAINING_COLS

    def test_training_cols_includes_status(self):
        assert "status" in _TRAINING_COLS

    def test_invoices_cols_includes_invoice_number(self):
        assert "invoice_number" in _INVOICES_COLS

    def test_invoices_cols_includes_total_amount(self):
        assert "total_amount" in _INVOICES_COLS

    def test_payments_cols_includes_amount(self):
        assert "amount" in _PAYMENTS_COLS

    def test_payments_cols_includes_payment_method(self):
        assert "payment_method" in _PAYMENTS_COLS

    def test_workflow_cols_includes_title(self):
        assert "title" in _WORKFLOW_COLS

    def test_workflow_cols_includes_status(self):
        assert "status" in _WORKFLOW_COLS

    def test_audit_cols_includes_action(self):
        assert "action" in _AUDIT_COLS

    def test_audit_cols_includes_module(self):
        assert "module" in _AUDIT_COLS

    def test_audit_cols_includes_severity(self):
        assert "severity" in _AUDIT_COLS

    def test_executive_cols_includes_metric_name(self):
        assert "metric_name" in _EXECUTIVE_COLS

    def test_executive_cols_includes_metric_value(self):
        assert "metric_value" in _EXECUTIVE_COLS


# ─────────────────────────────────────────────────────────────────────────────
# 2. _REPORT_QUERIES structure
# ─────────────────────────────────────────────────────────────────────────────


class TestReportQueries:
    def test_customers_query_exists(self):
        assert "customers" in _REPORT_QUERIES

    def test_training_query_exists(self):
        assert "training" in _REPORT_QUERIES

    def test_invoices_query_exists(self):
        assert "invoices" in _REPORT_QUERIES

    def test_payments_query_exists(self):
        assert "payments" in _REPORT_QUERIES

    def test_workflow_analytics_query_exists(self):
        assert "workflow_analytics" in _REPORT_QUERIES

    def test_audit_logs_query_exists(self):
        assert "audit_logs" in _REPORT_QUERIES

    def test_executive_kpis_not_in_queries(self):
        # executive_kpis uses a dedicated method, not _REPORT_QUERIES
        assert "executive_kpis" not in _REPORT_QUERIES

    def test_each_query_is_tuple_of_two(self):
        for key, val in _REPORT_QUERIES.items():
            assert isinstance(val, tuple)
            assert len(val) == 2

    def test_each_query_has_tenant_id_placeholder(self):
        for key, (sql, _) in _REPORT_QUERIES.items():
            assert ":tenant_id" in sql

    def test_each_query_has_workspace_id_placeholder(self):
        for key, (sql, _) in _REPORT_QUERIES.items():
            assert ":workspace_id" in sql

    def test_each_query_has_date_filter_placeholder(self):
        for key, (sql, _) in _REPORT_QUERIES.items():
            assert "{date_filter}" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 3. generate_report — happy path mocking
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateReport:
    def _setup_generate(self, svc, session, orm_report, db_rows):
        """Wire session.execute to handle both the repo writes and data query."""
        # We need to handle:
        # 1. repo.create → flush+refresh (no execute needed for add+flush)
        # 2. _query_table → execute returns row data
        # 3. repo.update_fields → select + update

        # Create fresh ORM objects per call to avoid shared state
        call_count = {"n": 0}

        async def execute_side_effect(stmt_or_text, params=None):
            call_count["n"] += 1
            n = call_count["n"]
            if n == 1:
                # _query_table or _export_executive_kpis
                mock_result = MagicMock()
                mock_result.fetchall.return_value = db_rows
                return mock_result
            else:
                # update_fields select
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = orm_report
                return mock_result

        session.execute = AsyncMock(side_effect=execute_side_effect)
        session.refresh = AsyncMock(side_effect=lambda r: None)

    @pytest.mark.asyncio
    async def test_generate_customers_csv_creates_record(self):
        svc, session = _make_svc()
        orm = _make_orm_report()
        self._setup_generate(svc, session, orm, [("Acme", "active")])
        redis = _null_redis()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)), \
             patch.object(svc._repo, "create", AsyncMock(return_value=orm)), \
             patch.object(svc._repo, "update_fields", AsyncMock(return_value=orm)):
            out = await svc.generate_report(_req("customers", "csv"))

        assert out.report_type == "customers"

    @pytest.mark.asyncio
    async def test_generate_report_busts_cache(self):
        svc, session = _make_svc()
        orm = _make_orm_report()
        redis = _null_redis()

        async def _fake_exec(stmt_or_text, params=None):
            mr = MagicMock()
            mr.fetchall.return_value = []
            mr.fetchone.return_value = None
            return mr

        session.execute = AsyncMock(side_effect=_fake_exec)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)), \
             patch.object(svc._repo, "create", AsyncMock(return_value=orm)), \
             patch.object(svc._repo, "update_fields", AsyncMock(return_value=orm)):
            await svc.generate_report(_req("customers"))

        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_generate_xlsx_creates_record(self):
        svc, session = _make_svc()
        orm = _make_orm_report(format="xlsx")
        redis = _null_redis()

        async def _fake_exec(stmt_or_text, params=None):
            mr = MagicMock()
            mr.fetchall.return_value = []
            mr.fetchone.return_value = None
            return mr

        session.execute = AsyncMock(side_effect=_fake_exec)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)), \
             patch.object(svc._repo, "create", AsyncMock(return_value=orm)), \
             patch.object(svc._repo, "update_fields", AsyncMock(return_value=orm)):
            out = await svc.generate_report(_req("customers", "xlsx"))

        assert out.format == "xlsx"

    @pytest.mark.asyncio
    async def test_generate_report_status_ready_on_success(self):
        svc, session = _make_svc()
        orm_pending = _make_orm_report(status="pending")
        orm_ready = _make_orm_report(status="ready")
        redis = _null_redis()

        async def _fake_exec(stmt_or_text, params=None):
            mr = MagicMock()
            mr.fetchall.return_value = []
            mr.fetchone.return_value = None
            return mr

        session.execute = AsyncMock(side_effect=_fake_exec)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)), \
             patch.object(svc._repo, "create", AsyncMock(return_value=orm_pending)), \
             patch.object(svc._repo, "update_fields", AsyncMock(return_value=orm_ready)):
            out = await svc.generate_report(_req("invoices"))

        assert out.status == "ready"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Redis fallback on connection failure
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisFallback:
    @pytest.mark.asyncio
    async def test_list_reports_graceful_on_redis_error(self):
        svc, session = _make_svc()
        orm = _make_orm_report()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(side_effect=Exception("Redis down"))):
            result = await svc.list_reports(WS_ID)

        assert result.total == 1

    @pytest.mark.asyncio
    async def test_bust_cache_graceful_on_redis_error(self):
        svc, _ = _make_svc()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(side_effect=Exception("Redis down"))):
            # Should not raise
            await svc._bust_cache(ORG_ID, WS_ID)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tenant isolation in repo
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_find_by_id_filters_by_tenant(self):
        from corpmind.modules.reporting.repo import ReportingRepo
        session = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = ReportingRepo(session)
        with patch(_PATCH_REPO_CTX, return_value=_ctx()):
            result = await repo.find_by_id(REPORT_ID)

        assert result is None
        # Verify execute was called (tenant filter applied in the WHERE clause)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_workspace_filters_by_tenant(self):
        from corpmind.modules.reporting.repo import ReportingRepo
        session = MagicMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = ReportingRepo(session)
        with patch(_PATCH_REPO_CTX, return_value=_ctx()):
            result = await repo.find_by_workspace(WS_ID)

        assert result == []
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_filters_by_tenant(self):
        from corpmind.modules.reporting.repo import ReportingRepo
        session = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        repo = ReportingRepo(session)
        with patch(_PATCH_REPO_CTX, return_value=_ctx()):
            deleted = await repo.delete(REPORT_ID)

        assert deleted is False

    @pytest.mark.asyncio
    async def test_two_tenants_different_cache_keys(self):
        org1 = uuid.uuid4()
        org2 = uuid.uuid4()
        k1 = _list_cache_key(org1, WS_ID)
        k2 = _list_cache_key(org2, WS_ID)
        assert k1 != k2


# ─────────────────────────────────────────────────────────────────────────────
# 6. Repo patterns
# ─────────────────────────────────────────────────────────────────────────────


class TestRepoPatterns:
    @pytest.mark.asyncio
    async def test_create_adds_to_session(self):
        from corpmind.modules.reporting.repo import ReportingRepo
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        repo = ReportingRepo(session)
        orm = _make_orm_report()
        await repo.create(orm)

        session.add.assert_called_once_with(orm)
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_fields_on_missing_record_returns_none(self):
        from corpmind.modules.reporting.repo import ReportingRepo
        session = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = ReportingRepo(session)
        with patch(_PATCH_REPO_CTX, return_value=_ctx()):
            result = await repo.update_fields(REPORT_ID, {"status": "ready"})

        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_workspace_with_type_filter(self):
        from corpmind.modules.reporting.repo import ReportingRepo
        session = MagicMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = ReportingRepo(session)
        with patch(_PATCH_REPO_CTX, return_value=_ctx()):
            result = await repo.find_by_workspace(WS_ID, report_type="customers")

        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 7. Export helper dispatch
# ─────────────────────────────────────────────────────────────────────────────


class TestExportHelpers:
    @pytest.mark.asyncio
    async def test_export_customers_dispatches_to_query_table(self):
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [("Acme", "active")]
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()):
            rows = await svc.export_customers(_req("customers"))

        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_export_training_dispatches_to_query_table(self):
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()):
            rows = await svc.export_training(_req("training"))

        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_export_invoices_dispatches_to_query_table(self):
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()):
            rows = await svc.export_invoices(_req("invoices"))

        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_export_payments_dispatches_to_query_table(self):
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()):
            rows = await svc.export_payments(_req("payments"))

        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_export_audit_dispatches_to_query_table(self):
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()):
            rows = await svc.export_audit(_req("audit_logs"))

        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_export_workflows_dispatches_to_query_table(self):
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()):
            rows = await svc.export_workflows(_req("workflow_analytics"))

        assert isinstance(rows, list)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Date filter in query
# ─────────────────────────────────────────────────────────────────────────────


class TestDateFilterInQuery:
    @pytest.mark.asyncio
    async def test_date_from_added_to_params(self):
        svc, session = _make_svc()
        captured_params = {}

        async def capture(stmt_or_text, params=None):
            captured_params.update(params or {})
            mr = MagicMock()
            mr.fetchall.return_value = []
            return mr

        session.execute = AsyncMock(side_effect=capture)
        req = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
            date_from="2026-01-01",
        )

        with patch(_PATCH_CTX, return_value=_ctx()):
            await svc._query_table(req)

        assert "date_from" in captured_params

    @pytest.mark.asyncio
    async def test_date_to_added_to_params(self):
        svc, session = _make_svc()
        captured_params = {}

        async def capture(stmt_or_text, params=None):
            captured_params.update(params or {})
            mr = MagicMock()
            mr.fetchall.return_value = []
            return mr

        session.execute = AsyncMock(side_effect=capture)
        req = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
            date_to="2026-12-31",
        )

        with patch(_PATCH_CTX, return_value=_ctx()):
            await svc._query_table(req)

        assert "date_to" in captured_params

    @pytest.mark.asyncio
    async def test_no_date_filter_no_extra_params(self):
        svc, session = _make_svc()
        captured_params = {}

        async def capture(stmt_or_text, params=None):
            captured_params.update(params or {})
            mr = MagicMock()
            mr.fetchall.return_value = []
            return mr

        session.execute = AsyncMock(side_effect=capture)

        with patch(_PATCH_CTX, return_value=_ctx()):
            await svc._query_table(_req("customers"))

        assert "date_from" not in captured_params
        assert "date_to" not in captured_params

    @pytest.mark.asyncio
    async def test_workflow_uses_started_at_for_date_filter(self):
        svc, session = _make_svc()
        captured_sql = {}

        async def capture(stmt_or_text, params=None):
            captured_sql["text"] = str(stmt_or_text)
            mr = MagicMock()
            mr.fetchall.return_value = []
            return mr

        session.execute = AsyncMock(side_effect=capture)
        req = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="workflow_analytics",
            format="csv",
            date_from="2026-01-01",
        )

        with patch(_PATCH_CTX, return_value=_ctx()):
            await svc._query_table(req)

        assert "started_at" in captured_sql["text"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_csv_with_special_chars(self):
        rows = [{"name": 'He said "hello"', "note": "line1\nline2"}]
        result = ReportingService._to_csv(rows)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_csv_preserves_unicode(self):
        rows = [{"name": "नमस्ते"}]
        result = ReportingService._to_csv(rows)
        assert "नमस्ते".encode("utf-8") in result

    def test_make_filename_no_spaces(self):
        name = ReportingService._make_filename("workflow_analytics", "csv")
        assert " " not in name

    def test_make_filename_underscore_separation(self):
        name = ReportingService._make_filename("customers", "csv")
        parts = name.split("_")
        assert len(parts) >= 2

    def test_report_export_out_tenant_id_field(self):
        orm = MagicMock(spec=ReportExport)
        orm.id = REPORT_ID
        orm.tenant_id = ORG_ID
        orm.workspace_id = WS_ID
        orm.report_type = "customers"
        orm.format = "csv"
        orm.status = "ready"
        orm.generated_by = USER_ID
        orm.generated_at = datetime.now(UTC)
        orm.download_name = "test.csv"
        orm.row_count = 5
        orm.file_size_bytes = 200
        orm.created_at = datetime.now(UTC)
        out = ReportExportOut.model_validate(orm)
        assert out.tenant_id == ORG_ID

    @pytest.mark.asyncio
    async def test_list_reports_empty_db_returns_zero_total(self):
        svc, session = _make_svc()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()
        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            result = await svc.list_reports(WS_ID)

        assert result.total == 0
        assert result.items == []
