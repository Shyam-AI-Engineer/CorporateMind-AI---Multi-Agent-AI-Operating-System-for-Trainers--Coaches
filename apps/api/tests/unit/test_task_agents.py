"""Unit tests for workers/tasks/agents.py — run_agent_workflow, refresh_churn_save_segments, reap_dead_letter_queue."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from corpmind.workers.tasks.agents import (
    reap_dead_letter_queue,
    refresh_churn_save_segments,
    run_agent_workflow,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _workflow_ids(**overrides):
    base = {
        "workflow_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "state": {"intent": "outreach", "campaign_id": str(uuid.uuid4())},
    }
    base.update(overrides)
    return base


# ── run_agent_workflow ─────────────────────────────────────────────────────────

class TestRunAgentWorkflow:
    def test_returns_completed_status(self):
        result = run_agent_workflow.run(**_workflow_ids())
        assert result["status"] == "completed"

    def test_returns_workflow_id_in_result(self):
        ids = _workflow_ids()
        result = run_agent_workflow.run(**ids)
        assert result["workflow_id"] == ids["workflow_id"]

    def test_task_key_logged_with_agent_prefix(self):
        ids = _workflow_ids()
        with patch("corpmind.workers.tasks.agents.log") as mock_log:
            run_agent_workflow.run(**ids)
        call_kwargs = mock_log.info.call_args.kwargs
        assert call_kwargs["task_key"] == f"agent:{ids['workflow_id']}"

    def test_tenant_id_logged_on_start(self):
        ids = _workflow_ids()
        with patch("corpmind.workers.tasks.agents.log") as mock_log:
            run_agent_workflow.run(**ids)
        call_kwargs = mock_log.info.call_args.kwargs
        assert call_kwargs["tenant_id"] == ids["tenant_id"]

    def test_accepts_empty_state(self):
        result = run_agent_workflow.run(**_workflow_ids(state={}))
        assert result["status"] == "completed"

    def test_accepts_complex_nested_state(self):
        state = {"intent": "analytics", "meta": {"nested": True, "count": 42}}
        result = run_agent_workflow.run(**_workflow_ids(state=state))
        assert result["workflow_id"] is not None


# ── refresh_churn_save_segments ────────────────────────────────────────────────

class TestRefreshChurnSaveSegments:
    def test_returns_none(self):
        result = refresh_churn_save_segments.run()
        assert result is None

    def test_logs_start_event(self):
        with patch("corpmind.workers.tasks.agents.log") as mock_log:
            refresh_churn_save_segments.run()
        mock_log.info.assert_called_once_with("crm.churn_save_refresh.start")


# ── reap_dead_letter_queue ─────────────────────────────────────────────────────

class TestReapDeadLetterQueue:
    def test_returns_none(self):
        result = reap_dead_letter_queue.run()
        assert result is None

    def test_logs_start_event(self):
        with patch("corpmind.workers.tasks.agents.log") as mock_log:
            reap_dead_letter_queue.run()
        mock_log.info.assert_called_once_with("dlq.reaper.start")
