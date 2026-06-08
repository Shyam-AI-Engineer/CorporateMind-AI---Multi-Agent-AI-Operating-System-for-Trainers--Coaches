"""Unit tests for sync_all_active_connections fan-out task and _run_fan_out.

All DB and broker calls are mocked.  Tests cover:
  - no active connections
  - single connection
  - multiple connections across different tenants
  - per-connection enqueue failure isolation
  - result shape (duration_ms, counts)
  - structured log emission
  - beat schedule configuration
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import structlog

from corpmind.workers.tasks.inbox import _run_fan_out

# ── Shared test identifiers ────────────────────────────────────────────────────

CONN_ID_1 = uuid.uuid4()
CONN_ID_2 = uuid.uuid4()
TENANT_ID_1 = uuid.uuid4()
TENANT_ID_2 = uuid.uuid4()
WS_ID_1 = uuid.uuid4()
WS_ID_2 = uuid.uuid4()


# ── Mock factories ─────────────────────────────────────────────────────────────

def _make_engine() -> MagicMock:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return engine


def _make_session(rows: list) -> AsyncMock:
    """Async context manager session that returns `rows` on execute()."""
    result = MagicMock()
    result.all.return_value = rows

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _db_patches(rows: list):
    """ExitStack context manager: patches engine + sessionmaker for _run_fan_out."""
    engine = _make_engine()
    session = _make_session(rows)
    factory = MagicMock(return_value=session)

    stack = ExitStack()
    stack.enter_context(
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engine)
    )
    stack.enter_context(
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=factory)
    )
    return stack, engine


# ── No active connections ──────────────────────────────────────────────────────

class TestNoActiveConnections:
    @pytest.mark.asyncio
    async def test_returns_zero_counts(self):
        stack, _ = _db_patches(rows=[])
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            result = await _run_fan_out()

        assert result["connections_scanned"] == 0
        assert result["syncs_queued"] == 0
        assert result["sync_failures"] == 0

    @pytest.mark.asyncio
    async def test_no_enqueue_calls(self):
        stack, _ = _db_patches(rows=[])
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            await _run_fan_out()

        mock_task.apply_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_engine_disposed_on_empty(self):
        stack, engine = _db_patches(rows=[])
        with stack, patch("corpmind.workers.tasks.inbox.sync_gmail_messages"):
            await _run_fan_out()

        engine.dispose.assert_awaited_once()


# ── Single active connection ───────────────────────────────────────────────────

class TestOneActiveConnection:
    @pytest.mark.asyncio
    async def test_scanned_and_queued_counts(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, _ = _db_patches(rows=rows)
        with stack, patch("corpmind.workers.tasks.inbox.sync_gmail_messages"):
            result = await _run_fan_out()

        assert result["connections_scanned"] == 1
        assert result["syncs_queued"] == 1
        assert result["sync_failures"] == 0

    @pytest.mark.asyncio
    async def test_apply_async_called_with_correct_kwargs(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            await _run_fan_out()

        mock_task.apply_async.assert_called_once()
        call_kwargs = mock_task.apply_async.call_args.kwargs["kwargs"]
        assert call_kwargs["connection_id"] == str(CONN_ID_1)
        assert call_kwargs["tenant_id"] == str(TENANT_ID_1)
        assert call_kwargs["workspace_id"] == str(WS_ID_1)
        # request_id is a freshly generated UUID — just assert it is a valid UUID string
        uuid.UUID(call_kwargs["request_id"])

    @pytest.mark.asyncio
    async def test_apply_async_targets_ingestion_queue(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            await _run_fan_out()

        call_kwargs = mock_task.apply_async.call_args.kwargs
        assert call_kwargs.get("queue") == "ingestion"


# ── Multiple active connections ────────────────────────────────────────────────

class TestMultipleActiveConnections:
    @pytest.mark.asyncio
    async def test_all_connections_enqueued(self):
        rows = [
            (CONN_ID_1, TENANT_ID_1, WS_ID_1),
            (CONN_ID_2, TENANT_ID_2, WS_ID_2),
        ]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            result = await _run_fan_out()

        assert result["connections_scanned"] == 2
        assert result["syncs_queued"] == 2
        assert result["sync_failures"] == 0
        assert mock_task.apply_async.call_count == 2

    @pytest.mark.asyncio
    async def test_each_connection_gets_unique_request_id(self):
        rows = [
            (CONN_ID_1, TENANT_ID_1, WS_ID_1),
            (CONN_ID_2, TENANT_ID_2, WS_ID_2),
        ]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            await _run_fan_out()

        calls = mock_task.apply_async.call_args_list
        request_id_1 = calls[0].kwargs["kwargs"]["request_id"]
        request_id_2 = calls[1].kwargs["kwargs"]["request_id"]
        assert request_id_1 != request_id_2

    @pytest.mark.asyncio
    async def test_correct_tenant_ids_passed_per_connection(self):
        rows = [
            (CONN_ID_1, TENANT_ID_1, WS_ID_1),
            (CONN_ID_2, TENANT_ID_2, WS_ID_2),
        ]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            await _run_fan_out()

        calls = mock_task.apply_async.call_args_list
        enqueued_tenants = {c.kwargs["kwargs"]["tenant_id"] for c in calls}
        assert str(TENANT_ID_1) in enqueued_tenants
        assert str(TENANT_ID_2) in enqueued_tenants


# ── Failure isolation ──────────────────────────────────────────────────────────

class TestEnqueueFailureIsolation:
    @pytest.mark.asyncio
    async def test_one_failing_connection_does_not_block_others(self):
        """apply_async raises on CONN_ID_1; CONN_ID_2 must still be enqueued."""
        rows = [
            (CONN_ID_1, TENANT_ID_1, WS_ID_1),
            (CONN_ID_2, TENANT_ID_2, WS_ID_2),
        ]
        stack, _ = _db_patches(rows=rows)

        call_count = 0

        def _apply_async_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("broker connection refused")

        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            mock_task.apply_async.side_effect = _apply_async_side_effect
            result = await _run_fan_out()

        assert result["syncs_queued"] == 1
        assert result["sync_failures"] == 1
        assert result["connections_scanned"] == 2

    @pytest.mark.asyncio
    async def test_all_failing_connections_counted(self):
        rows = [
            (CONN_ID_1, TENANT_ID_1, WS_ID_1),
            (CONN_ID_2, TENANT_ID_2, WS_ID_2),
        ]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            mock_task.apply_async.side_effect = RuntimeError("broker down")
            result = await _run_fan_out()

        assert result["syncs_queued"] == 0
        assert result["sync_failures"] == 2

    @pytest.mark.asyncio
    async def test_engine_disposed_even_on_enqueue_failure(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, engine = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            mock_task.apply_async.side_effect = RuntimeError("broker down")
            await _run_fan_out()

        engine.dispose.assert_awaited_once()


# ── Result shape ───────────────────────────────────────────────────────────────

class TestResultShape:
    @pytest.mark.asyncio
    async def test_duration_ms_is_non_negative_int(self):
        stack, _ = _db_patches(rows=[])
        with stack, patch("corpmind.workers.tasks.inbox.sync_gmail_messages"):
            result = await _run_fan_out()

        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_all_expected_keys_present(self):
        stack, _ = _db_patches(rows=[])
        with stack, patch("corpmind.workers.tasks.inbox.sync_gmail_messages"):
            result = await _run_fan_out()

        assert set(result.keys()) == {
            "connections_scanned",
            "syncs_queued",
            "sync_failures",
            "duration_ms",
        }


# ── Logging behavior ───────────────────────────────────────────────────────────

class TestLoggingBehavior:
    @pytest.mark.asyncio
    async def test_completion_event_logged(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, _ = _db_patches(rows=rows)
        with stack, patch("corpmind.workers.tasks.inbox.sync_gmail_messages"):
            with structlog.testing.capture_logs() as cap:
                await _run_fan_out()

        complete_events = [e for e in cap if e["event"] == "inbox.fan_out.complete"]
        assert len(complete_events) == 1
        ev = complete_events[0]
        assert ev["connections_scanned"] == 1
        assert ev["syncs_queued"] == 1
        assert ev["sync_failures"] == 0
        assert "duration_ms" in ev

    @pytest.mark.asyncio
    async def test_per_connection_queued_event_logged(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, _ = _db_patches(rows=rows)
        with stack, patch("corpmind.workers.tasks.inbox.sync_gmail_messages"):
            with structlog.testing.capture_logs() as cap:
                await _run_fan_out()

        queued_events = [e for e in cap if e["event"] == "inbox.fan_out.queued"]
        assert len(queued_events) == 1
        assert queued_events[0]["connection_id"] == str(CONN_ID_1)
        assert queued_events[0]["tenant_id"] == str(TENANT_ID_1)

    @pytest.mark.asyncio
    async def test_enqueue_failure_error_logged(self):
        rows = [(CONN_ID_1, TENANT_ID_1, WS_ID_1)]
        stack, _ = _db_patches(rows=rows)
        with stack, patch(
            "corpmind.workers.tasks.inbox.sync_gmail_messages"
        ) as mock_task:
            mock_task.apply_async.side_effect = RuntimeError("broker down")
            with structlog.testing.capture_logs() as cap:
                await _run_fan_out()

        error_events = [e for e in cap if e["event"] == "inbox.fan_out.enqueue_failed"]
        assert len(error_events) == 1
        assert error_events[0]["connection_id"] == str(CONN_ID_1)
        assert "broker down" in error_events[0]["error"]


# ── Beat schedule configuration ────────────────────────────────────────────────

class TestScheduleConfiguration:
    def test_beat_schedule_entry_exists(self):
        import corpmind.workers.celery_beat_schedule  # noqa: F401 — triggers schedule registration
        from corpmind.workers.celery_app import app

        entry = app.conf.beat_schedule.get("inbox.sync_all_active_connections")
        assert entry is not None

    def test_beat_schedule_points_to_correct_task(self):
        import corpmind.workers.celery_beat_schedule  # noqa: F401
        from corpmind.workers.celery_app import app

        entry = app.conf.beat_schedule["inbox.sync_all_active_connections"]
        assert entry["task"] == "corpmind.workers.tasks.inbox.sync_all_active_connections"

    def test_beat_schedule_uses_ingestion_queue(self):
        import corpmind.workers.celery_beat_schedule  # noqa: F401
        from corpmind.workers.celery_app import app

        entry = app.conf.beat_schedule["inbox.sync_all_active_connections"]
        assert entry["options"]["queue"] == "ingestion"

    def test_beat_schedule_interval_matches_settings(self):
        from datetime import timedelta

        import corpmind.workers.celery_beat_schedule  # noqa: F401
        from corpmind.core.config import settings
        from corpmind.workers.celery_app import app

        entry = app.conf.beat_schedule["inbox.sync_all_active_connections"]
        assert entry["schedule"] == timedelta(seconds=settings.INBOX_SYNC_INTERVAL_SECONDS)

    def test_default_interval_is_300_seconds(self):
        from corpmind.core.config import settings

        assert settings.INBOX_SYNC_INTERVAL_SECONDS == 300
