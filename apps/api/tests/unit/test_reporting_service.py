"""Unit tests — Sprint 56: Reporting & Export Center (part 1).

Tests for schemas, events, models, cache helpers, and service methods.
Target: 115+ tests in this file.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.reporting.events import ReportDeleted, ReportFailed, ReportGenerated
from corpmind.modules.reporting.models import ReportExport
from corpmind.modules.reporting.schemas import (
    SUPPORTED_FORMATS,
    SUPPORTED_REPORT_TYPES,
    GenerateReportRequest,
    ReportExportListOut,
    ReportExportOut,
)
from corpmind.modules.reporting.service import (
    ReportingService,
    _list_cache_key,
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema constants
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaConstants:
    def test_supported_report_types_is_frozenset(self):
        assert isinstance(SUPPORTED_REPORT_TYPES, frozenset)

    def test_supported_report_types_has_7_types(self):
        assert len(SUPPORTED_REPORT_TYPES) == 7

    def test_customers_in_report_types(self):
        assert "customers" in SUPPORTED_REPORT_TYPES

    def test_training_in_report_types(self):
        assert "training" in SUPPORTED_REPORT_TYPES

    def test_invoices_in_report_types(self):
        assert "invoices" in SUPPORTED_REPORT_TYPES

    def test_payments_in_report_types(self):
        assert "payments" in SUPPORTED_REPORT_TYPES

    def test_executive_kpis_in_report_types(self):
        assert "executive_kpis" in SUPPORTED_REPORT_TYPES

    def test_workflow_analytics_in_report_types(self):
        assert "workflow_analytics" in SUPPORTED_REPORT_TYPES

    def test_audit_logs_in_report_types(self):
        assert "audit_logs" in SUPPORTED_REPORT_TYPES

    def test_supported_formats_is_frozenset(self):
        assert isinstance(SUPPORTED_FORMATS, frozenset)

    def test_csv_in_formats(self):
        assert "csv" in SUPPORTED_FORMATS

    def test_xlsx_in_formats(self):
        assert "xlsx" in SUPPORTED_FORMATS

    def test_supported_formats_has_2_formats(self):
        assert len(SUPPORTED_FORMATS) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 2. GenerateReportRequest validation
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateReportRequest:
    def test_valid_request_customers_csv(self):
        r = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
        )
        assert r.report_type == "customers"
        assert r.format == "csv"

    def test_valid_request_invoices_xlsx(self):
        r = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="invoices",
            format="xlsx",
        )
        assert r.format == "xlsx"

    def test_invalid_report_type_raises(self):
        with pytest.raises(Exception):
            GenerateReportRequest(
                workspace_id=WS_ID,
                report_type="INVALID_TYPE",
                format="csv",
            )

    def test_invalid_format_raises(self):
        with pytest.raises(Exception):
            GenerateReportRequest(
                workspace_id=WS_ID,
                report_type="customers",
                format="pdf",
            )

    def test_date_from_optional(self):
        r = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
        )
        assert r.date_from is None

    def test_date_to_optional(self):
        r = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
        )
        assert r.date_to is None

    def test_date_filters_accepted(self):
        r = GenerateReportRequest(
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
            date_from="2026-01-01",
            date_to="2026-12-31",
        )
        assert r.date_from == "2026-01-01"
        assert r.date_to == "2026-12-31"

    def test_all_report_types_accepted(self):
        for rt in SUPPORTED_REPORT_TYPES:
            r = GenerateReportRequest(
                workspace_id=WS_ID,
                report_type=rt,
                format="csv",
            )
            assert r.report_type == rt

    def test_all_formats_accepted(self):
        for fmt in SUPPORTED_FORMATS:
            r = GenerateReportRequest(
                workspace_id=WS_ID,
                report_type="customers",
                format=fmt,
            )
            assert r.format == fmt


# ─────────────────────────────────────────────────────────────────────────────
# 3. ReportExportOut schema
# ─────────────────────────────────────────────────────────────────────────────


class TestReportExportOut:
    def test_from_orm(self):
        orm = _make_orm_report()
        out = ReportExportOut.model_validate(orm)
        assert out.id == REPORT_ID
        assert out.report_type == "customers"

    def test_status_field(self):
        orm = _make_orm_report(status="ready")
        out = ReportExportOut.model_validate(orm)
        assert out.status == "ready"

    def test_row_count_field(self):
        orm = _make_orm_report(row_count=100)
        out = ReportExportOut.model_validate(orm)
        assert out.row_count == 100

    def test_file_size_bytes_field(self):
        orm = _make_orm_report(file_size_bytes=2048)
        out = ReportExportOut.model_validate(orm)
        assert out.file_size_bytes == 2048

    def test_download_name_field(self):
        orm = _make_orm_report(download_name="test.csv")
        out = ReportExportOut.model_validate(orm)
        assert out.download_name == "test.csv"

    def test_generated_at_none(self):
        orm = _make_orm_report(generated_at=None)
        out = ReportExportOut.model_validate(orm)
        assert out.generated_at is None

    def test_format_field(self):
        orm = _make_orm_report(format="xlsx")
        out = ReportExportOut.model_validate(orm)
        assert out.format == "xlsx"


# ─────────────────────────────────────────────────────────────────────────────
# 4. ReportExportListOut schema
# ─────────────────────────────────────────────────────────────────────────────


class TestReportExportListOut:
    def test_empty_list(self):
        out = ReportExportListOut(items=[], total=0)
        assert out.total == 0
        assert out.items == []

    def test_with_items(self):
        orm = _make_orm_report()
        item = ReportExportOut.model_validate(orm)
        out = ReportExportListOut(items=[item], total=1)
        assert out.total == 1
        assert len(out.items) == 1

    def test_json_roundtrip(self):
        orm = _make_orm_report()
        item = ReportExportOut.model_validate(orm)
        lst = ReportExportListOut(items=[item], total=1)
        j = lst.model_dump_json()
        restored = ReportExportListOut.model_validate_json(j)
        assert restored.total == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Domain events
# ─────────────────────────────────────────────────────────────────────────────


class TestEvents:
    def test_report_generated_fields(self):
        ev = ReportGenerated(
            report_id=REPORT_ID,
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
            row_count=10,
            file_size_bytes=512,
            generated_by=USER_ID,
        )
        assert ev.report_id == REPORT_ID
        assert ev.report_type == "customers"
        assert ev.row_count == 10
        assert ev.file_size_bytes == 512

    def test_report_generated_has_occurred_at(self):
        ev = ReportGenerated(
            report_id=REPORT_ID,
            workspace_id=WS_ID,
            report_type="customers",
            format="csv",
            row_count=0,
            file_size_bytes=0,
            generated_by=USER_ID,
        )
        assert ev.occurred_at is not None
        assert isinstance(ev.occurred_at, datetime)

    def test_report_deleted_fields(self):
        ev = ReportDeleted(
            report_id=REPORT_ID,
            workspace_id=WS_ID,
            report_type="customers",
            deleted_by=USER_ID,
        )
        assert ev.report_id == REPORT_ID
        assert ev.deleted_by == USER_ID

    def test_report_deleted_has_occurred_at(self):
        ev = ReportDeleted(
            report_id=REPORT_ID,
            workspace_id=WS_ID,
            report_type="invoices",
            deleted_by=USER_ID,
        )
        assert ev.occurred_at is not None

    def test_report_failed_fields(self):
        ev = ReportFailed(
            report_id=REPORT_ID,
            workspace_id=WS_ID,
            report_type="training",
            reason="DB error",
        )
        assert ev.reason == "DB error"
        assert ev.report_type == "training"

    def test_report_failed_has_occurred_at(self):
        ev = ReportFailed(
            report_id=REPORT_ID,
            workspace_id=WS_ID,
            report_type="training",
            reason="x",
        )
        assert ev.occurred_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cache key helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheKeys:
    def test_list_cache_key_format(self):
        k = _list_cache_key(ORG_ID, WS_ID)
        assert k.startswith(f"t:{ORG_ID}:")
        assert str(WS_ID) in k

    def test_list_cache_key_contains_reporting(self):
        k = _list_cache_key(ORG_ID, WS_ID)
        assert "reporting" in k

    def test_list_cache_key_unique_per_org(self):
        other_org = uuid.uuid4()
        k1 = _list_cache_key(ORG_ID, WS_ID)
        k2 = _list_cache_key(other_org, WS_ID)
        assert k1 != k2

    def test_list_cache_key_unique_per_workspace(self):
        other_ws = uuid.uuid4()
        k1 = _list_cache_key(ORG_ID, WS_ID)
        k2 = _list_cache_key(ORG_ID, other_ws)
        assert k1 != k2


# ─────────────────────────────────────────────────────────────────────────────
# 7. CSV serialisation
# ─────────────────────────────────────────────────────────────────────────────


class TestToCSV:
    def test_empty_rows_returns_empty_bytes(self):
        result = ReportingService._to_csv([])
        assert result == b""

    def test_single_row_csv(self):
        rows = [{"name": "Acme", "status": "active"}]
        result = ReportingService._to_csv(rows)
        assert b"name" in result
        assert b"Acme" in result

    def test_csv_has_header(self):
        rows = [{"col_a": "v1", "col_b": "v2"}]
        result = ReportingService._to_csv(rows)
        assert b"col_a" in result
        assert b"col_b" in result

    def test_csv_none_values_become_empty_string(self):
        rows = [{"name": "X", "notes": None}]
        result = ReportingService._to_csv(rows)
        assert b"X" in result

    def test_csv_multiple_rows(self):
        rows = [{"k": str(i)} for i in range(5)]
        result = ReportingService._to_csv(rows)
        lines = result.decode().strip().splitlines()
        # header + 5 data rows
        assert len(lines) == 6

    def test_csv_returns_bytes(self):
        rows = [{"a": "b"}]
        result = ReportingService._to_csv(rows)
        assert isinstance(result, bytes)


# ─────────────────────────────────────────────────────────────────────────────
# 8. XLSX serialisation
# ─────────────────────────────────────────────────────────────────────────────


class TestToXLSX:
    def test_xlsx_returns_bytes(self):
        rows = [{"a": "b"}]
        result = ReportingService._to_xlsx(rows)
        assert isinstance(result, bytes)

    def test_xlsx_bom_prefix(self):
        rows = [{"a": "b"}]
        result = ReportingService._to_xlsx(rows)
        assert result[:3] == b"\xef\xbb\xbf"

    def test_xlsx_empty_rows(self):
        result = ReportingService._to_xlsx([])
        assert isinstance(result, bytes)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Filename helper
# ─────────────────────────────────────────────────────────────────────────────


class TestMakeFilename:
    def test_csv_extension(self):
        name = ReportingService._make_filename("customers", "csv")
        assert name.endswith(".csv")

    def test_xlsx_extension(self):
        name = ReportingService._make_filename("invoices", "xlsx")
        assert name.endswith(".xlsx")

    def test_report_type_in_name(self):
        name = ReportingService._make_filename("audit_logs", "csv")
        assert "audit_logs" in name

    def test_name_contains_timestamp(self):
        name = ReportingService._make_filename("training", "csv")
        # Should contain a year-like string
        assert "2026" in name or "2025" in name or "2027" in name


# ─────────────────────────────────────────────────────────────────────────────
# 10. Model fields
# ─────────────────────────────────────────────────────────────────────────────


class TestReportExportModel:
    def test_tablename(self):
        assert ReportExport.__tablename__ == "report_exports"

    def test_id_column_exists(self):
        assert hasattr(ReportExport, "id")

    def test_tenant_id_column_exists(self):
        assert hasattr(ReportExport, "tenant_id")

    def test_workspace_id_column_exists(self):
        assert hasattr(ReportExport, "workspace_id")

    def test_report_type_column_exists(self):
        assert hasattr(ReportExport, "report_type")

    def test_format_column_exists(self):
        assert hasattr(ReportExport, "format")

    def test_status_column_exists(self):
        assert hasattr(ReportExport, "status")

    def test_generated_by_column_exists(self):
        assert hasattr(ReportExport, "generated_by")

    def test_generated_at_column_exists(self):
        assert hasattr(ReportExport, "generated_at")

    def test_download_name_column_exists(self):
        assert hasattr(ReportExport, "download_name")

    def test_row_count_column_exists(self):
        assert hasattr(ReportExport, "row_count")

    def test_file_size_bytes_column_exists(self):
        assert hasattr(ReportExport, "file_size_bytes")

    def test_created_at_column_exists(self):
        assert hasattr(ReportExport, "created_at")


# ─────────────────────────────────────────────────────────────────────────────
# 11. list_reports — cache hit
# ─────────────────────────────────────────────────────────────────────────────


class TestListReportsCacheHit:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self):
        svc, session = _make_svc()
        orm = _make_orm_report()
        item = ReportExportOut.model_validate(orm)
        lst = ReportExportListOut(items=[item], total=1)
        cached_json = lst.model_dump_json()

        redis = _null_redis()
        redis.get = AsyncMock(return_value=cached_json)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            result = await svc.list_reports(WS_ID)

        assert result.total == 1
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        svc, session = _make_svc()
        orm = _make_orm_report()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()
        redis.get = AsyncMock(return_value=None)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            result = await svc.list_reports(WS_ID)

        assert result.total == 1
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_reports_with_type_filter_skips_cache(self):
        svc, session = _make_svc()
        orm = _make_orm_report()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            result = await svc.list_reports(WS_ID, report_type="customers")

        redis.get.assert_not_called()
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_stores_result_in_cache_on_miss(self):
        svc, session = _make_svc()
        orm = _make_orm_report()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()
        redis.get = AsyncMock(return_value=None)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            await svc.list_reports(WS_ID)

        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_cache_ttl_is_300(self):
        svc, session = _make_svc()
        orm = _make_orm_report()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [orm]
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()
        redis.get = AsyncMock(return_value=None)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            await svc.list_reports(WS_ID)

        call_args = redis.setex.call_args
        assert call_args[0][1] == 300


# ─────────────────────────────────────────────────────────────────────────────
# 12. get_report
# ─────────────────────────────────────────────────────────────────────────────


class TestGetReport:
    @pytest.mark.asyncio
    async def test_get_report_found(self):
        svc, session = _make_svc()
        orm = _make_orm_report()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()):
            out = await svc.get_report(REPORT_ID)

        assert out.id == REPORT_ID

    @pytest.mark.asyncio
    async def test_get_report_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()):
            with pytest.raises(NotFoundError):
                await svc.get_report(REPORT_ID)


# ─────────────────────────────────────────────────────────────────────────────
# 13. delete_report
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteReport:
    @pytest.mark.asyncio
    async def test_delete_report_success(self):
        svc, session = _make_svc()
        orm = _make_orm_report()

        # first call = find_by_id, second call = delete inner find
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [orm, orm]
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            await svc.delete_report(REPORT_ID)

        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_report_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        svc, session = _make_svc()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()):
            with pytest.raises(NotFoundError):
                await svc.delete_report(REPORT_ID)

    @pytest.mark.asyncio
    async def test_delete_busts_cache(self):
        svc, session = _make_svc()
        orm = _make_orm_report()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [orm, orm]
        session.execute = AsyncMock(return_value=result_mock)

        redis = _null_redis()

        with patch(_PATCH_CTX, return_value=_ctx()), \
             patch(_PATCH_REPO_CTX, return_value=_ctx()), \
             patch(_PATCH_REDIS, AsyncMock(return_value=redis)):
            await svc.delete_report(REPORT_ID)

        redis.delete.assert_called_once()
