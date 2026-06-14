"""Unit tests for OutreachAgent graph nodes (Sprint 10).

Node-level tests drive each node directly so failures are immediately
attributable.  Full-graph tests go through BaseAgent.run() → compiled.ainvoke()
to exercise the conditional routing logic.

Patch strategy (all lazy imports are patched at their source module):
  OutreachService methods   → patch.object(OutreachService, ...)
  TrainerVectorStore        → corpmind.ai.trainer_vector_store.TrainerVectorStore
  EuriClient                → corpmind.ai.euri_client.EuriClient
  ComplianceGuardAgent      → corpmind.agents.compliance_guard.ComplianceGuardAgent
  OutboundMessageRepo       → corpmind.modules.outreach.repo.OutboundMessageRepo
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.agents.outreach_agent import OutreachAgent
from corpmind.agents.state import SCHEMA_VERSION, AgentState, default_state
from corpmind.modules.outreach.service import OutreachService

pytestmark = pytest.mark.asyncio

# ── Shared constants ───────────────────────────────────────────────────────────

_ORG_ID = uuid.uuid4()
_WS_ID = uuid.uuid4()
_CONTACT_ID = uuid.uuid4()
_CAMPAIGN_ID = uuid.uuid4()

_TRAINER_ROW: dict = {
    "niche": "Leadership Development",
    "topics": ["executive coaching", "strategic thinking"],
    "tone": "semi_formal",
    "pricing_min_inr": 50_000,
    "pricing_max_inr": 200_000,
    "bio": "10 years in L&D at Fortune 500 companies.",
    "usp": "Proven ROI in 90 days.",
    "target_industries": ["Banking", "Insurance"],
}

_CONTACT_ROW: dict = {
    "id": str(_CONTACT_ID),
    "full_name": "Priya Sharma",
    "title": "VP-HR",
    "email": "priya@hdfc.example",
    "is_contactable": True,
    "preferred_language": "en",
    "company_name": "HDFC Life Insurance",
    "industry": "Insurance",
}

_COPY_JSON = json.dumps(
    {
        "subject": "Leadership bench at HDFC Life",
        "body": "Hi Priya, I help insurance HR teams build leadership benches quickly.",
        "tone_used": "semi_formal",
        "language_used": "en",
    }
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_agent(session=None) -> OutreachAgent:
    return OutreachAgent(session=session or _make_session())


def _base_state(**overrides) -> AgentState:
    state = default_state(
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        user_id=uuid.uuid4(),
        request_id="req-test-001",
        run_id="run-test-001",
    )
    state["contact_id"] = str(_CONTACT_ID)
    state["campaign_id"] = str(_CAMPAIGN_ID)
    state["channel"] = "email"
    state.update(overrides)
    return state


def _mock_tvs(score: float = 0.85, raise_exc: Exception | None = None) -> MagicMock:
    """Return a mock TrainerVectorStore instance."""
    store = MagicMock()
    if raise_exc is not None:
        store.search_profiles = AsyncMock(side_effect=raise_exc)
    else:
        store.search_profiles = AsyncMock(
            return_value=[{"score": score, "profile_id": str(uuid.uuid4()), "payload": {}}]
        )
    store.aclose = AsyncMock()
    return store


# ── Tests: AgentState schema additions ────────────────────────────────────────


class TestAgentStateSchema:
    def test_schema_version_is_3(self):
        # Bumped to 3 in Sprint 11A when discovered_company_ids + qualify_score_threshold were added.
        assert SCHEMA_VERSION == 3

    def test_default_state_has_new_fields(self):
        state = _base_state()
        assert "contact_id" in state
        assert "trainer_context" in state
        assert "contact_context" in state
        assert "trainer_qdrant_score" in state

    def test_default_qdrant_score_is_zero(self):
        state = _base_state()
        assert state["trainer_qdrant_score"] == 0.0

    def test_default_contexts_are_empty_dicts(self):
        state = _base_state()
        assert state["trainer_context"] == {}
        assert state["contact_context"] == {}


# ── Tests: _load_context ───────────────────────────────────────────────────────


class TestLoadContext:
    async def test_populates_trainer_and_contact_context(self):
        agent = _make_agent()
        state = _base_state()

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs()),
        ):
            result = await agent._load_context(state)

        assert result["trainer_context"] == _TRAINER_ROW
        assert result["contact_context"] == _CONTACT_ROW
        assert result["trainer_niche"] == "Leadership Development"
        assert result["trainer_tone"] == "semi_formal"
        assert result["trainer_topics"] == ["executive coaching", "strategic thinking"]
        assert result["last_node"] == "load_context"

    async def test_qdrant_score_set_on_success(self):
        agent = _make_agent()
        state = _base_state()

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs(score=0.92)),
        ):
            result = await agent._load_context(state)

        assert result["trainer_qdrant_score"] == pytest.approx(0.92)

    async def test_qdrant_failure_is_graceful(self):
        """Qdrant down → score=0.0, SQL results unaffected, no exception raised."""
        agent = _make_agent()
        state = _base_state()

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch(
                "corpmind.ai.trainer_vector_store.TrainerVectorStore",
                return_value=_mock_tvs(raise_exc=RuntimeError("Qdrant connection refused")),
            ),
        ):
            result = await agent._load_context(state)  # must not raise

        assert result["trainer_qdrant_score"] == 0.0
        assert result["trainer_context"] == _TRAINER_ROW  # SQL unaffected
        assert result.get("status") != "failed"

    async def test_missing_contact_id_continues_with_empty_contact(self):
        """No contact_id → contact fetch skipped, node still completes."""
        agent = _make_agent()
        state = _base_state()
        state["contact_id"] = None

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs()),
        ):
            result = await agent._load_context(state)

        assert result["contact_context"] == {}
        assert result["last_node"] == "load_context"

    async def test_qdrant_query_uses_title_and_company(self):
        """Verify the semantic query is built from title + company + industry."""
        agent = _make_agent()
        state = _base_state()
        mock_store = _mock_tvs()

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=mock_store),
        ):
            await agent._load_context(state)

        call_kwargs = mock_store.search_profiles.call_args.kwargs
        query = call_kwargs["query"]
        assert "VP-HR" in query
        assert "HDFC Life Insurance" in query
        assert "Insurance" in query


# ── Tests: _generate_variants ──────────────────────────────────────────────────


class TestGenerateVariants:
    async def test_calls_euri_with_correct_task_and_prompt(self):
        agent = _make_agent()
        state = _base_state()
        state["trainer_context"] = _TRAINER_ROW
        state["contact_context"] = _CONTACT_ROW

        with patch("corpmind.ai.euri_client.EuriClient") as MockEC:
            MockEC.return_value.chat = AsyncMock(return_value={"content": _COPY_JSON})
            await agent._generate_variants(state)

        call_kwargs = MockEC.return_value.chat.call_args.kwargs
        assert call_kwargs["task"] == "outreach_copy"
        assert call_kwargs["prompt_name"] == "outreach.email"

    async def test_sets_final_output(self):
        agent = _make_agent()
        state = _base_state()
        state["trainer_context"] = _TRAINER_ROW
        state["contact_context"] = _CONTACT_ROW

        with patch("corpmind.ai.euri_client.EuriClient") as MockEC:
            MockEC.return_value.chat = AsyncMock(return_value={"content": _COPY_JSON})
            result = await agent._generate_variants(state)

        assert result["final_output"]["subject"] == "Leadership bench at HDFC Life"
        assert "Priya" in result["final_output"]["body"]
        assert result["final_output"]["ab_variant"] == "A"

    async def test_malformed_json_sets_status_failed(self):
        agent = _make_agent()
        state = _base_state()
        state["trainer_context"] = _TRAINER_ROW
        state["contact_context"] = _CONTACT_ROW

        with patch("corpmind.ai.euri_client.EuriClient") as MockEC:
            MockEC.return_value.chat = AsyncMock(return_value={"content": "not json {"})
            result = await agent._generate_variants(state)

        assert result["status"] == "failed"
        assert "non-JSON" in result["error"]
        assert result["last_node"] == "generate_variants"

    async def test_missing_context_sets_status_failed(self):
        """Empty trainer_context / contact_context → fail before the LLM call."""
        agent = _make_agent()
        state = _base_state()
        # trainer_context and contact_context left as {} (default_state defaults)

        result = await agent._generate_variants(state)

        assert result["status"] == "failed"
        assert result["error"]


# ── Tests: _persist_messages ───────────────────────────────────────────────────


class TestPersistMessages:
    async def test_creates_outbound_message_and_commits(self):
        session = _make_session()
        agent = _make_agent(session=session)
        state = _base_state()
        state["final_output"] = {
            "subject": "Test subject",
            "body": "Test body content.",
            "ab_variant": "A",
        }

        with patch("corpmind.modules.outreach.repo.OutboundMessageRepo") as MockRepo:
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo
            result = await agent._persist_messages(state)

        mock_repo.create.assert_awaited_once()
        session.commit.assert_awaited_once()
        assert len(result["outreach_message_ids"]) == 1
        assert result["status"] == "completed"
        assert result["last_node"] == "persist_messages"

    async def test_no_final_output_skips_repo(self):
        """No final_output → skip persistence, still complete cleanly."""
        session = _make_session()
        agent = _make_agent(session=session)
        state = _base_state()
        # final_output is None from default_state

        with patch("corpmind.modules.outreach.repo.OutboundMessageRepo") as MockRepo:
            result = await agent._persist_messages(state)

        MockRepo.assert_not_called()
        session.commit.assert_not_awaited()
        assert result["status"] == "completed"

    async def test_no_session_sets_status_failed(self):
        agent = OutreachAgent(session=None)
        state = _base_state()
        state["final_output"] = {"subject": "X", "body": "Y", "ab_variant": "A"}

        result = await agent._persist_messages(state)

        assert result["status"] == "failed"
        assert "session" in result["error"].lower()


# ── Tests: full graph via BaseAgent.run() ─────────────────────────────────────


class TestFullGraph:
    async def test_full_graph_compliance_allowed_path(self):
        """load_context → generate_variants → compliance(allowed) → persist → completed."""
        session = _make_session()
        agent = _make_agent(session=session)
        state = _base_state()

        mock_guard = MagicMock()
        mock_guard.run = AsyncMock(
            side_effect=lambda s, c: {**s, "compliance_outcome": "allowed"}
        )

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs()),
            patch("corpmind.ai.euri_client.EuriClient") as MockEC,
            patch("corpmind.agents.compliance_guard.ComplianceGuardAgent", return_value=mock_guard),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo") as MockRepo,
        ):
            MockEC.return_value.chat = AsyncMock(return_value={"content": _COPY_JSON})
            mock_repo = AsyncMock()
            MockRepo.return_value = mock_repo

            result = await agent.run(state, {})

        assert result["status"] == "completed"
        assert len(result.get("outreach_message_ids", [])) == 1
        mock_repo.create.assert_awaited_once()

    async def test_compliance_blocked_path_skips_persistence(self):
        """compliance_outcome=blocked → persist_messages never called."""
        session = _make_session()
        agent = _make_agent(session=session)
        state = _base_state()

        mock_guard = MagicMock()
        mock_guard.run = AsyncMock(
            side_effect=lambda s, c: {
                **s,
                "compliance_outcome": "blocked",
                "compliance_reason": "unsubscribed",
            }
        )

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs()),
            patch("corpmind.ai.euri_client.EuriClient") as MockEC,
            patch("corpmind.agents.compliance_guard.ComplianceGuardAgent", return_value=mock_guard),
            patch("corpmind.modules.outreach.repo.OutboundMessageRepo") as MockRepo,
        ):
            MockEC.return_value.chat = AsyncMock(return_value={"content": _COPY_JSON})

            result = await agent.run(state, {})

        MockRepo.assert_not_called()
        assert result.get("compliance_outcome") == "blocked"

    async def test_generation_failure_short_circuits_before_compliance(self):
        """Bad JSON from LLM → status=failed, compliance gate never called."""
        session = _make_session()
        agent = _make_agent(session=session)
        state = _base_state()

        mock_guard = MagicMock()
        mock_guard.run = AsyncMock(
            side_effect=lambda s, c: {**s, "compliance_outcome": "allowed"}
        )

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs()),
            patch("corpmind.ai.euri_client.EuriClient") as MockEC,
            patch("corpmind.agents.compliance_guard.ComplianceGuardAgent", return_value=mock_guard),
        ):
            MockEC.return_value.chat = AsyncMock(return_value={"content": "not json {"})

            result = await agent.run(state, {})

        mock_guard.run.assert_not_awaited()
        assert result.get("status") == "failed"


# ── Smoke test ─────────────────────────────────────────────────────────────────


class TestSmoke:
    async def test_trainer_niche_and_topics_flow_into_prompt_inputs(self):
        """Full chain: SQL profile → Qdrant retrieval → prompt_inputs → draft.

        Verifies that the trainer's niche and topics survive the full path from
        SQL fetch through _build_prompt_inputs and arrive in the prompt_inputs
        dict that EuriClient.chat receives — closing the Sprint 9A indexing loop.
        """
        session = _make_session()
        agent = _make_agent(session=session)
        state = _base_state()

        captured_inputs: dict = {}

        async def _capture_chat(*, task, prompt_name, prompt_inputs, **kwargs):
            captured_inputs.update(prompt_inputs)
            return {"content": _COPY_JSON}

        with (
            patch.object(OutreachService, "_fetch_contact", AsyncMock(return_value=_CONTACT_ROW)),
            patch.object(OutreachService, "_fetch_trainer_profile", AsyncMock(return_value=_TRAINER_ROW)),
            patch("corpmind.ai.trainer_vector_store.TrainerVectorStore", return_value=_mock_tvs(score=0.78)),
            patch("corpmind.ai.euri_client.EuriClient") as MockEC,
        ):
            MockEC.return_value.chat = AsyncMock(side_effect=_capture_chat)

            # Drive the two nodes that form the retrieval → generation chain.
            state = await agent._load_context(state)
            state = await agent._generate_variants(state)

        # Trainer intelligence from SQL profile reaches prompt_inputs.
        assert captured_inputs["trainer_niche"] == "Leadership Development"
        assert "executive coaching" in captured_inputs["trainer_topics"]

        # Contact context also reaches prompt_inputs.
        assert captured_inputs["contact_company"] == "HDFC Life Insurance"
        assert captured_inputs["contact_industry"] == "Insurance"

        # Draft exists in state; pipeline did not fail.
        assert state.get("final_output") is not None
        assert state["final_output"]["body"]
        assert state.get("status") != "failed"

        # Qdrant score is surfaced in state (observability).
        assert state["trainer_qdrant_score"] == pytest.approx(0.78)
