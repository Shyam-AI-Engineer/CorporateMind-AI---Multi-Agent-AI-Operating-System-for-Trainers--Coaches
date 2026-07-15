"""Unit tests — Bulk Operations CSV import persistence (RC Hotfix #1).

Verifies that import_csv() actually INSERTs validated rows into the destination
entity tables. Tests are pure-Python (no DB, no Redis); all I/O is mocked.

Coverage targets:
  ✓ customers imported
  ✓ training_engagements imported
  ✓ business_tasks imported
  ✓ workflow_templates imported
  ✓ partial validation failures — valid rows still inserted
  ✓ transaction rollback — INSERT error marks operation failed
  ✓ successful_records equals inserted rows
  ✓ processed_records correct
  ✓ duplicate rows both inserted (no dedup at service layer)
  ✓ tenant isolation — tenant_id injected into every row
  ✓ cache behaviour unchanged — invalidated on import, not used for result
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from corpmind.modules.bulk_operations.schemas import CsvImportRequest
from corpmind.modules.bulk_operations.service import (
    BulkOperationService,
    _ALL_INSERT_COLUMNS,
    _CSV_TO_DB_RENAME,
    _INSERT_DEFAULTS,
    _build_entity_values,
)

ORG = uuid.uuid4()
WS = uuid.uuid4()
USER = uuid.uuid4()
NOW = datetime.now(UTC)


# ── Helpers ───────────────────────────────────────────────────────────────────

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
        total_records=1,
        processed_records=1,
        successful_records=1,
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
    """Return (service, session) with begin_nested correctly mocked."""
    session = AsyncMock()
    nested = AsyncMock()
    nested.__aexit__ = AsyncMock(return_value=False)  # propagate exceptions
    session.begin_nested = MagicMock(return_value=nested)
    return BulkOperationService(session), session


def _capture_update_svc(entity_type: str = "customers"):
    """Service whose update_fields side_effect captures the call args dict."""
    svc, session = _make_svc()
    svc._repo = AsyncMock()

    created_op = _make_op(entity_type=entity_type, status="running",
                          successful_records=0, failed_records=0)
    svc._repo.create.return_value = created_op

    captured: dict = {}

    async def fake_update(op_id, fields):
        captured.update(fields)
        return _make_op(
            entity_type=entity_type,
            status=fields["status"],
            processed_records=fields["processed_records"],
            successful_records=fields["successful_records"],
            failed_records=fields["failed_records"],
            error_summary=fields.get("error_summary"),
        )

    svc._repo.update_fields.side_effect = fake_update
    return svc, session, captured


# ── _build_entity_values unit tests ──────────────────────────────────────────

class TestBuildEntityValues:
    def test_customers_required_fields_present(self):
        row = {"company_name": "Acme", "display_name": "Acme Corp"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["company_name"] == "Acme"
        assert values["display_name"] == "Acme Corp"

    def test_customers_system_fields_injected(self):
        row = {"company_name": "X", "display_name": "Y"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["tenant_id"] == str(ORG)
        assert values["workspace_id"] == str(WS)
        assert values["id"] is not None
        assert values["created_at"] == NOW.isoformat()
        assert values["updated_at"] == NOW.isoformat()

    def test_customers_id_is_unique_per_call(self):
        row = {"company_name": "X", "display_name": "Y"}
        v1 = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        v2 = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert v1["id"] != v2["id"]

    def test_customers_default_status_active(self):
        row = {"company_name": "X", "display_name": "Y"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["status"] == "active"

    def test_customers_csv_status_overrides_default(self):
        row = {"company_name": "X", "display_name": "Y", "status": "churned"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["status"] == "churned"

    def test_customers_default_health_status_healthy(self):
        row = {"company_name": "X", "display_name": "Y"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["health_status"] == "healthy"

    def test_customers_optional_fields_default_to_none(self):
        row = {"company_name": "X", "display_name": "Y"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["industry"] is None
        assert values["notes"] is None
        assert values["email"] is None

    def test_customers_optional_field_populated(self):
        row = {"company_name": "X", "display_name": "Y", "industry": "SaaS",
               "email": "ceo@acme.com"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert values["industry"] == "SaaS"
        assert values["email"] == "ceo@acme.com"

    def test_customers_unknown_csv_field_excluded(self):
        row = {"company_name": "X", "display_name": "Y",
               "hacker_injection": "'; DROP TABLE customers;--"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert "hacker_injection" not in values

    def test_customers_result_keys_match_all_insert_columns(self):
        row = {"company_name": "X", "display_name": "Y"}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        assert set(values.keys()) == set(_ALL_INSERT_COLUMNS["customers"])

    def test_training_engagements_title_renamed_to_program_name(self):
        cid = str(uuid.uuid4())
        row = {"title": "Leadership", "start_date": "2026-08-01", "customer_id": cid}
        values = _build_entity_values(row, "training_engagements", ORG, WS, USER, NOW)
        assert values["program_name"] == "Leadership"
        assert "title" not in values

    def test_training_engagements_start_date_renamed_to_planned_start_date(self):
        cid = str(uuid.uuid4())
        row = {"title": "T", "start_date": "2026-09-15", "customer_id": cid}
        values = _build_entity_values(row, "training_engagements", ORG, WS, USER, NOW)
        assert values["planned_start_date"] == "2026-09-15"
        assert "start_date" not in values

    def test_training_engagements_defaults_applied(self):
        cid = str(uuid.uuid4())
        row = {"title": "T", "start_date": "2026-08-01", "customer_id": cid}
        values = _build_entity_values(row, "training_engagements", ORG, WS, USER, NOW)
        assert values["training_type"] == "imported"
        assert values["delivery_mode"] == "other"
        assert values["status"] == "planned"
        assert values["priority"] == "medium"

    def test_training_engagements_customer_id_from_row(self):
        cid = str(uuid.uuid4())
        row = {"title": "T", "start_date": "2026-08-01", "customer_id": cid}
        values = _build_entity_values(row, "training_engagements", ORG, WS, USER, NOW)
        assert values["customer_id"] == cid

    def test_training_engagements_customer_id_none_when_absent(self):
        row = {"title": "T", "start_date": "2026-08-01"}
        values = _build_entity_values(row, "training_engagements", ORG, WS, USER, NOW)
        assert values["customer_id"] is None  # will fail DB NOT NULL check — expected

    def test_business_tasks_defaults(self):
        row = {"title": "Deploy RC1", "status": "open"}
        values = _build_entity_values(row, "business_tasks", ORG, WS, USER, NOW)
        assert values["title"] == "Deploy RC1"
        assert values["status"] == "open"
        assert values["priority"] == "medium"
        assert values["created_by"] == "bulk_import"

    def test_business_tasks_csv_priority_overrides_default(self):
        row = {"title": "T", "status": "open", "priority": "high"}
        values = _build_entity_values(row, "business_tasks", ORG, WS, USER, NOW)
        assert values["priority"] == "high"

    def test_business_tasks_no_updated_at_in_workflow_templates(self):
        row = {"name": "Onboard", "trigger_event": "customer.created"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        assert "updated_at" not in values

    def test_workflow_templates_active_status_maps_to_is_active_true(self):
        row = {"name": "Onboard", "trigger_event": "e", "status": "active"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        assert values["is_active"] is True

    def test_workflow_templates_inactive_status_maps_to_is_active_false(self):
        row = {"name": "Onboard", "trigger_event": "e", "status": "inactive"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        assert values["is_active"] is False

    def test_workflow_templates_draft_status_maps_to_is_active_false(self):
        row = {"name": "Onboard", "trigger_event": "e", "status": "draft"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        assert values["is_active"] is False

    def test_workflow_templates_trigger_event_excluded(self):
        row = {"name": "Onboard", "trigger_event": "customer.created"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        # trigger_event is validated but has no DB column — must NOT appear in INSERT
        assert "trigger_event" not in values

    def test_workflow_templates_created_by_is_requested_by(self):
        row = {"name": "Onboard", "trigger_event": "e"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        assert values["created_by"] == str(USER)

    def test_workflow_templates_result_keys_match_all_insert_columns(self):
        row = {"name": "Onboard", "trigger_event": "e"}
        values = _build_entity_values(row, "workflow_templates", ORG, WS, USER, NOW)
        assert set(values.keys()) == set(_ALL_INSERT_COLUMNS["workflow_templates"])

    def test_tenant_id_always_from_context_not_csv(self):
        other_org = uuid.uuid4()
        row = {"company_name": "X", "display_name": "Y", "tenant_id": str(other_org)}
        values = _build_entity_values(row, "customers", ORG, WS, USER, NOW)
        # CSV-supplied tenant_id must be ignored; system value wins
        assert values["tenant_id"] == str(ORG)


# ── import_csv persistence tests ──────────────────────────────────────────────

class TestImportCsvCustomers:
    @pytest.mark.asyncio
    async def test_execute_called_for_each_valid_row(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "Acme", "display_name": "Acme Corp"},
                    {"company_name": "Beta", "display_name": "Beta Ltd"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        # session.execute should be called twice (one INSERT per row)
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_insert_sql_targets_customers_table(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        sql_str = str(session.execute.call_args[0][0])
        assert "customers" in sql_str
        assert "INSERT INTO" in sql_str.upper()

    @pytest.mark.asyncio
    async def test_successful_records_equals_inserted_rows(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},
                    {"company_name": "C", "display_name": "D"},
                    {"company_name": "E", "display_name": "F"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert captured["successful_records"] == 3
        assert captured["status"] == "completed"

    @pytest.mark.asyncio
    async def test_processed_records_correct_all_valid(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},
                    {"company_name": "C", "display_name": "D"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert captured["processed_records"] == 2
        assert captured["failed_records"] == 0

    @pytest.mark.asyncio
    async def test_partial_failures_valid_rows_still_inserted(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},  # valid
                    {"company_name": "C"},                         # invalid (missing display_name)
                    {"company_name": "D", "display_name": "E"},  # valid
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        # 2 valid rows → 2 INSERT calls
        assert session.execute.await_count == 2
        assert captured["successful_records"] == 2
        assert captured["failed_records"] == 1
        assert captured["processed_records"] == 3
        assert captured["status"] == "completed"

    @pytest.mark.asyncio
    async def test_tenant_id_injected_in_insert_params(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["tenant_id"] == str(ORG)
        assert params["workspace_id"] == str(WS)

    @pytest.mark.asyncio
    async def test_begin_nested_called_when_valid_rows_exist(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        session.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_rows_both_inserted(self, monkeypatch):
        """Two rows with identical data are both inserted with distinct UUIDs."""
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        row = {"company_name": "Acme", "display_name": "Acme Corp"}
        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[row, row],  # identical rows
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert session.execute.await_count == 2
        assert captured["successful_records"] == 2
        # IDs must differ
        params_calls = [c[0][1] for c in session.execute.call_args_list]
        assert params_calls[0]["id"] != params_calls[1]["id"]


class TestImportCsvTrainingEngagements:
    @pytest.mark.asyncio
    async def test_execute_called_for_each_valid_row(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        cid = str(uuid.uuid4())
        svc, session, captured = _capture_update_svc("training_engagements")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="training_engagements",
                rows=[
                    {"title": "T1", "start_date": "2026-08-01", "customer_id": cid},
                    {"title": "T2", "start_date": "2026-09-01", "customer_id": cid},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_insert_sql_targets_training_engagements_table(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("training_engagements")
        cid = str(uuid.uuid4())

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="training_engagements",
                rows=[{"title": "T", "start_date": "2026-08-01", "customer_id": cid}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        sql_str = str(session.execute.call_args[0][0])
        assert "training_engagements" in sql_str

    @pytest.mark.asyncio
    async def test_title_renamed_to_program_name_in_params(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("training_engagements")
        cid = str(uuid.uuid4())

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="training_engagements",
                rows=[{"title": "Leadership", "start_date": "2026-08-01",
                       "customer_id": cid}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["program_name"] == "Leadership"
        assert "title" not in params

    @pytest.mark.asyncio
    async def test_start_date_renamed_to_planned_start_date(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("training_engagements")
        cid = str(uuid.uuid4())

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="training_engagements",
                rows=[{"title": "T", "start_date": "2026-08-01", "customer_id": cid}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["planned_start_date"] == "2026-08-01"
        assert "start_date" not in params

    @pytest.mark.asyncio
    async def test_successful_records_correct(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("training_engagements")
        cid = str(uuid.uuid4())

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="training_engagements",
                rows=[
                    {"title": "T1", "start_date": "2026-08-01", "customer_id": cid},
                    {"title": "T2", "start_date": "2026-09-01", "customer_id": cid},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert captured["successful_records"] == 2
        assert captured["failed_records"] == 0


class TestImportCsvBusinessTasks:
    @pytest.mark.asyncio
    async def test_execute_called_for_valid_rows(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("business_tasks")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="business_tasks",
                rows=[
                    {"title": "Fix bug", "status": "open"},
                    {"title": "Write docs", "status": "in_progress"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert session.execute.await_count == 2
        assert captured["successful_records"] == 2

    @pytest.mark.asyncio
    async def test_insert_sql_targets_business_tasks_table(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("business_tasks")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="business_tasks",
                rows=[{"title": "T", "status": "open"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        sql_str = str(session.execute.call_args[0][0])
        assert "business_tasks" in sql_str

    @pytest.mark.asyncio
    async def test_created_by_defaults_to_bulk_import(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("business_tasks")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="business_tasks",
                rows=[{"title": "T", "status": "open"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["created_by"] == "bulk_import"

    @pytest.mark.asyncio
    async def test_invalid_row_not_inserted(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("business_tasks")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="business_tasks",
                rows=[
                    {"title": "Valid", "status": "open"},
                    {"status": "open"},               # invalid: missing title
                    {"title": "Also Valid", "status": "completed"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        # only 2 valid rows → 2 INSERT calls
        assert session.execute.await_count == 2
        assert captured["failed_records"] == 1
        assert captured["successful_records"] == 2


class TestImportCsvWorkflowTemplates:
    @pytest.mark.asyncio
    async def test_execute_called_for_valid_rows(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("workflow_templates")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="workflow_templates",
                rows=[
                    {"name": "Onboard", "trigger_event": "customer.created"},
                    {"name": "Renew", "trigger_event": "contract.expiring"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert session.execute.await_count == 2
        assert captured["successful_records"] == 2

    @pytest.mark.asyncio
    async def test_insert_sql_targets_workflow_templates_table(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("workflow_templates")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="workflow_templates",
                rows=[{"name": "Onboard", "trigger_event": "e"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        sql_str = str(session.execute.call_args[0][0])
        assert "workflow_templates" in sql_str

    @pytest.mark.asyncio
    async def test_active_status_maps_to_is_active_true_in_params(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("workflow_templates")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="workflow_templates",
                rows=[{"name": "N", "trigger_event": "e", "status": "active"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["is_active"] is True

    @pytest.mark.asyncio
    async def test_inactive_status_maps_to_is_active_false(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("workflow_templates")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="workflow_templates",
                rows=[{"name": "N", "trigger_event": "e", "status": "inactive"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["is_active"] is False

    @pytest.mark.asyncio
    async def test_trigger_event_not_in_insert_params(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("workflow_templates")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="workflow_templates",
                rows=[{"name": "N", "trigger_event": "customer.created"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert "trigger_event" not in params

    @pytest.mark.asyncio
    async def test_created_by_is_requested_by_uuid(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("workflow_templates")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="workflow_templates",
                rows=[{"name": "N", "trigger_event": "e"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        params = session.execute.call_args[0][1]
        assert params["created_by"] == str(USER)


# ── Transaction rollback tests ─────────────────────────────────────────────────

class TestImportCsvTransactionRollback:
    @pytest.mark.asyncio
    async def test_insert_error_marks_operation_failed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        # Make the INSERT raise a DB error
        session.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
        # begin_nested.__aexit__ must propagate the exception (return_value=False)

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            out = await svc.import_csv(req)

        assert out.status == "failed"
        assert captured["status"] == "failed"

    @pytest.mark.asyncio
    async def test_insert_error_sets_successful_to_zero(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")
        session.execute = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},
                    {"company_name": "C", "display_name": "D"},
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert captured["successful_records"] == 0

    @pytest.mark.asyncio
    async def test_insert_error_counts_valid_rows_as_failed(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")
        session.execute = AsyncMock(side_effect=RuntimeError("unique violation"))

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "A", "display_name": "B"},  # valid
                    {"company_name": "C", "display_name": "D"},  # valid
                    {"company_name": "E"},                         # invalid
                ],
                requested_by=USER,
            )
            await svc.import_csv(req)

        # 1 validation failure + 2 valid rows that failed to insert = 3 failed total
        assert captured["failed_records"] == 3
        assert captured["successful_records"] == 0

    @pytest.mark.asyncio
    async def test_insert_error_stored_in_error_summary(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")
        session.execute = AsyncMock(side_effect=RuntimeError("null value in column"))

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        assert captured.get("error_summary") is not None
        assert "Insert failed" in captured["error_summary"]


# ── stop_on_error skips INSERT ────────────────────────────────────────────────

class TestImportCsvStopOnError:
    @pytest.mark.asyncio
    async def test_stop_on_error_with_failures_skips_insert(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "Bad"},             # invalid — triggers stop
                    {"company_name": "A", "display_name": "B"},  # never reached
                ],
                requested_by=USER,
                stop_on_error=True,
            )
            await svc.import_csv(req)

        # No INSERT should be attempted
        assert session.execute.await_count == 0
        assert captured["status"] == "failed"
        assert captured["successful_records"] == 0

    @pytest.mark.asyncio
    async def test_stop_on_error_false_inserts_valid_rows_despite_failures(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, captured = _capture_update_svc("customers")

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=AsyncMock()):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[
                    {"company_name": "Bad"},                      # invalid
                    {"company_name": "A", "display_name": "B"},   # valid
                ],
                requested_by=USER,
                stop_on_error=False,
            )
            await svc.import_csv(req)

        # 1 valid row must be inserted even though 1 row was invalid
        assert session.execute.await_count == 1
        assert captured["successful_records"] == 1
        assert captured["failed_records"] == 1
        assert captured["status"] == "completed"


# ── cache behaviour ───────────────────────────────────────────────────────────

class TestImportCsvCache:
    @pytest.mark.asyncio
    async def test_cache_invalidated_on_import(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("customers")
        mock_redis = AsyncMock()

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=mock_redis):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_not_read_during_import(self, monkeypatch):
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("customers")
        mock_redis = AsyncMock()

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=mock_redis):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        mock_redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_not_set_after_import(self, monkeypatch):
        """import_csv never populates the list cache (that's list_operations' job)."""
        monkeypatch.setattr(
            "corpmind.modules.bulk_operations.service.get_tenant_context", _make_ctx
        )
        svc, session, _ = _capture_update_svc("customers")
        mock_redis = AsyncMock()

        with patch("corpmind.modules.bulk_operations.service.get_redis",
                   return_value=mock_redis):
            req = CsvImportRequest(
                workspace_id=WS, entity_type="customers",
                rows=[{"company_name": "A", "display_name": "B"}],
                requested_by=USER,
            )
            await svc.import_csv(req)

        mock_redis.set.assert_not_awaited()
