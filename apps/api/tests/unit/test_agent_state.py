"""Unit tests for agents/state.py — SCHEMA_VERSION, PlanStep, Plan, AgentState, default_state."""

from __future__ import annotations

import uuid

import pytest

from corpmind.agents.state import (
    SCHEMA_VERSION,
    AgentState,
    Plan,
    PlanStep,
    default_state,
)


# ── SCHEMA_VERSION ─────────────────────────────────────────────────────────────

class TestSchemaVersion:
    def test_is_int(self):
        assert isinstance(SCHEMA_VERSION, int)

    def test_is_positive(self):
        assert SCHEMA_VERSION >= 1


# ── PlanStep ───────────────────────────────────────────────────────────────────

class TestPlanStep:
    def _make(self, **overrides):
        base = dict(
            tool="send_email",
            inputs={"to": "test@example.com"},
            expected_output_schema={"type": "object"},
            status="pending",
            result=None,
        )
        base.update(overrides)
        return PlanStep(**base)

    def test_instantiation_with_required_fields(self):
        step = self._make()
        assert step["tool"] == "send_email"
        assert step["status"] == "pending"
        assert step["result"] is None

    def test_status_lifecycle_values(self):
        for status in ("pending", "running", "done", "failed"):
            step = self._make(status=status)
            assert step["status"] == status

    def test_result_accepts_arbitrary_dict(self):
        step = self._make(status="done", result={"extracted_chars": 1234, "format": "pdf"})
        assert step["result"]["extracted_chars"] == 1234

    def test_inputs_can_be_nested(self):
        step = self._make(inputs={"payload": {"campaign_id": str(uuid.uuid4())}})
        assert "campaign_id" in step["inputs"]["payload"]

    def test_expected_output_schema_can_be_empty(self):
        step = self._make(expected_output_schema={})
        assert step["expected_output_schema"] == {}


# ── Plan ───────────────────────────────────────────────────────────────────────

class TestPlan:
    def _step(self, tool="noop", status="pending"):
        return PlanStep(tool=tool, inputs={}, expected_output_schema={},
                        status=status, result=None)

    def test_empty_steps(self):
        plan = Plan(steps=[], current_step_index=0, created_at="2026-06-01T01:00:00Z")
        assert plan["steps"] == []
        assert plan["current_step_index"] == 0

    def test_with_multiple_steps(self):
        steps = [self._step("discover"), self._step("send")]
        plan = Plan(steps=steps, current_step_index=1, created_at="2026-06-01T01:00:00Z")
        assert len(plan["steps"]) == 2
        assert plan["steps"][1]["tool"] == "send"

    def test_created_at_is_iso_string(self):
        plan = Plan(steps=[], current_step_index=0, created_at="2026-06-01T01:00:00+00:00")
        assert isinstance(plan["created_at"], str)
        assert "T" in plan["created_at"]

    def test_current_step_index_can_be_nonzero(self):
        steps = [self._step(), self._step(), self._step()]
        plan = Plan(steps=steps, current_step_index=2, created_at="2026-06-01T00:00:00Z")
        assert plan["current_step_index"] == 2


# ── AgentState ────────────────────────────────────────────────────────────────

class TestAgentState:
    def test_empty_state_is_valid(self):
        # total=False means every field is optional
        state: AgentState = {}
        assert state == {}

    def test_partial_identifiers(self):
        state: AgentState = {
            "tenant_id": str(uuid.uuid4()),
            "request_id": "req-abc",
            "status": "running",
        }
        assert state["status"] == "running"

    def test_compliance_fields(self):
        state: AgentState = {
            "compliance_checked": True,
            "compliance_outcome": "allowed",
            "compliance_reason": None,
            "compliance_audit_id": str(uuid.uuid4()),
        }
        assert state["compliance_checked"] is True
        assert state["compliance_outcome"] == "allowed"

    def test_hitl_fields(self):
        state: AgentState = {
            "hitl_required": True,
            "hitl_reason": "recipient_count_exceeded",
            "hitl_approved_by": None,
            "hitl_approved_at": None,
        }
        assert state["hitl_required"] is True

    def test_cost_tracking_fields(self):
        state: AgentState = {
            "total_tokens_in": 1234,
            "total_tokens_out": 456,
            "total_cost_inr": 2.50,
        }
        assert state["total_tokens_in"] == 1234
        assert state["total_cost_inr"] == pytest.approx(2.50)

    def test_all_status_values(self):
        for s in ("running", "paused_hitl", "completed", "failed"):
            state: AgentState = {"status": s}
            assert state["status"] == s

    def test_list_fields_accept_values(self):
        state: AgentState = {
            "trainer_topics": ["leadership", "sales"],
            "discovered_contact_ids": [str(uuid.uuid4())],
            "outreach_message_ids": [],
        }
        assert len(state["trainer_topics"]) == 2

    def test_plan_field_accepts_none_and_plan(self):
        state_none: AgentState = {"plan": None}
        assert state_none["plan"] is None

        plan = Plan(steps=[], current_step_index=0, created_at="2026-06-01T00:00:00Z")
        state_with_plan: AgentState = {"plan": plan}
        assert state_with_plan["plan"]["current_step_index"] == 0

    def test_final_output_accepts_dict(self):
        state: AgentState = {"final_output": {"sent": 5, "blocked": 0}}
        assert state["final_output"]["sent"] == 5


# ── default_state factory ──────────────────────────────────────────────────────

class TestDefaultState:
    def _call(self, **overrides):
        params = dict(
            tenant_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            request_id="req-default-test",
            run_id="run-default-test",
        )
        params.update(overrides)
        return default_state(**params)

    def test_returns_dict(self):
        state = self._call()
        assert isinstance(state, dict)

    def test_schema_version_matches_module_constant(self):
        state = self._call()
        assert state["schema_version"] == SCHEMA_VERSION

    def test_ids_stored_as_strings(self):
        t_id = uuid.uuid4()
        w_id = uuid.uuid4()
        u_id = uuid.uuid4()
        state = self._call(tenant_id=t_id, workspace_id=w_id, user_id=u_id)
        assert state["tenant_id"] == str(t_id)
        assert state["workspace_id"] == str(w_id)
        assert state["user_id"] == str(u_id)

    def test_request_id_and_run_id_stored(self):
        state = default_state(
            tenant_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            request_id="req-x",
            run_id="run-x",
        )
        assert state["request_id"] == "req-x"
        assert state["run_id"] == "run-x"

    def test_status_defaults_to_running(self):
        assert self._call()["status"] == "running"

    def test_compliance_defaults_unchecked(self):
        state = self._call()
        assert state["compliance_checked"] is False
        assert state["compliance_outcome"] is None
        assert state["compliance_reason"] is None
        assert state["compliance_audit_id"] is None

    def test_hitl_defaults_false(self):
        state = self._call()
        assert state["hitl_required"] is False
        assert state["hitl_reason"] is None
        assert state["hitl_approved_by"] is None
        assert state["hitl_approved_at"] is None

    def test_token_counters_default_zero(self):
        state = self._call()
        assert state["total_tokens_in"] == 0
        assert state["total_tokens_out"] == 0
        assert state["total_cost_inr"] == 0.0

    def test_list_fields_default_empty(self):
        state = self._call()
        for key in (
            "trainer_topics", "target_industries", "target_employee_ranges",
            "discovered_contact_ids", "qualified_contact_ids",
            "outreach_message_ids", "ab_variants",
        ):
            assert state[key] == [], f"{key} should default to []"

    def test_plan_defaults_none(self):
        assert self._call()["plan"] is None

    def test_nullable_string_fields_default_none(self):
        state = self._call()
        for key in (
            "trainer_profile_id", "trainer_niche", "trainer_tone",
            "campaign_id", "channel",
            "proposal_id", "proposal_contact_id",
            "error", "last_node", "final_output",
        ):
            assert state[key] is None, f"{key} should default to None"

    def test_retry_count_defaults_zero(self):
        assert self._call()["retry_count"] == 0

    def test_intent_and_goal_default_empty_strings(self):
        state = self._call()
        assert state["intent"] == ""
        assert state["user_goal"] == ""
        assert state["intent_confidence"] == 0.0
