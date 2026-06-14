"""Unit tests for HRDiscoveryAgent.

Test matrix:
  TestAgentStateSchema   — SCHEMA_VERSION=3, new fields, correct defaults
  TestDiscoverCompanies  — found, empty-pool log, filter match/miss, no-session guard
  TestFindContacts       — fan-out across companies, deduplication, no-contacts path
  TestQualify            — score filtering, threshold, cap-at-50, final_output, failure path
  TestFullGraph          — success, no-companies short-circuit, no-contacts short-circuit
  TestSmoke              — full pipeline; qualified_contact_ids ⊆ discovered_contact_ids
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.agents.hr_discovery_agent import HRDiscoveryAgent
from corpmind.agents.state import SCHEMA_VERSION, AgentState, default_state
from corpmind.modules.hr_discovery.repo import CompanyRepo, HRContactRepo
from corpmind.modules.hr_discovery.service import HRDiscoveryService

pytestmark = pytest.mark.asyncio

# ── Shared test constants ─────────────────────────────────────────────────────

_ORG_ID = str(uuid.uuid4())
_WS_ID = str(uuid.uuid4())
_USER_ID = str(uuid.uuid4())

_COMPANY_A_ID = str(uuid.uuid4())
_COMPANY_B_ID = str(uuid.uuid4())
_CONTACT_A_ID = str(uuid.uuid4())
_CONTACT_B_ID = str(uuid.uuid4())
_CONTACT_C_ID = str(uuid.uuid4())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_company(id_str: str, industry: str = "BFSI") -> MagicMock:
    obj = MagicMock()
    obj.id = uuid.UUID(id_str)
    obj.name = f"Company-{id_str[:8]}"
    obj.industry = industry
    obj.employee_count_range = "500-1000"
    return obj


def _make_contact(id_str: str, company_id_str: str) -> MagicMock:
    obj = MagicMock()
    obj.id = uuid.UUID(id_str)
    obj.company_id = uuid.UUID(company_id_str)
    obj.full_name = f"Contact-{id_str[:8]}"
    obj.title = "VP HR"
    obj.email = "contact@example.com"
    obj.is_contactable = True
    obj.email_deliverable = True
    return obj


def _make_ranking_response(contacts_with_scores: list[tuple[str, int]]) -> MagicMock:
    response = MagicMock()
    rankings = []
    for contact_id_str, score in contacts_with_scores:
        r = MagicMock()
        r.contact_id = uuid.UUID(contact_id_str)
        r.score = score
        r.reason = f"Reason for score {score}"
        rankings.append(r)
    response.rankings = rankings
    return response


def _make_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    return session


def _make_agent(session: MagicMock | None = None) -> HRDiscoveryAgent:
    return HRDiscoveryAgent(session=session)


def _base_state(**overrides: object) -> AgentState:
    state = AgentState(
        schema_version=SCHEMA_VERSION,
        request_id="req-test-discovery",
        run_id="run-test-discovery",
        tenant_id=_ORG_ID,
        workspace_id=_WS_ID,
        user_id=_USER_ID,
        trainer_niche="Leadership Development",
        trainer_topics=["Executive Coaching", "Strategic Thinking"],
        target_industries=["BFSI", "Insurance"],
        target_employee_ranges=["500-1000"],
        discovered_company_ids=[],
        discovered_contact_ids=[],
        qualified_contact_ids=[],
        qualify_score_threshold=5,
        status="running",
    )
    state.update(overrides)  # type: ignore[typeddict-unknown-key]
    return state


# ── TestAgentStateSchema ──────────────────────────────────────────────────────

class TestAgentStateSchema:
    def test_schema_version_is_3(self) -> None:
        assert SCHEMA_VERSION == 3

    def test_discovered_company_ids_default_is_empty_list(self) -> None:
        state = default_state(
            tenant_id=uuid.UUID(_ORG_ID),
            workspace_id=uuid.UUID(_WS_ID),
            user_id=uuid.UUID(_USER_ID),
            request_id="req",
            run_id="run",
        )
        assert state["discovered_company_ids"] == []

    def test_qualify_score_threshold_default_is_5(self) -> None:
        state = default_state(
            tenant_id=uuid.UUID(_ORG_ID),
            workspace_id=uuid.UUID(_WS_ID),
            user_id=uuid.UUID(_USER_ID),
            request_id="req",
            run_id="run",
        )
        assert state["qualify_score_threshold"] == 5

    def test_schema_version_in_default_state(self) -> None:
        state = default_state(
            tenant_id=uuid.UUID(_ORG_ID),
            workspace_id=uuid.UUID(_WS_ID),
            user_id=uuid.UUID(_USER_ID),
            request_id="req",
            run_id="run",
        )
        assert state["schema_version"] == 3


# ── TestDiscoverCompanies ─────────────────────────────────────────────────────

class TestDiscoverCompanies:
    async def test_companies_found_populates_discovered_company_ids(self) -> None:
        agent = _make_agent(session=_make_session())
        companies = [_make_company(_COMPANY_A_ID), _make_company(_COMPANY_B_ID)]

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(return_value=companies)):
            state = await agent._discover_companies(_base_state())

        assert state["discovered_company_ids"] == [_COMPANY_A_ID, _COMPANY_B_ID]
        assert state.get("status") != "failed"
        assert state.get("status") != "completed"

    async def test_empty_result_sets_status_completed(self) -> None:
        agent = _make_agent(session=_make_session())

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(return_value=[])):
            state = await agent._discover_companies(_base_state())

        assert state["discovered_company_ids"] == []
        assert state["status"] == "completed"

    async def test_empty_tenant_pool_logs_warning(self) -> None:
        """When the tenant has no companies at all, log empty_company_pool."""
        agent = _make_agent(session=_make_session())

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(return_value=[])):
            with patch("corpmind.agents.hr_discovery_agent.log") as mock_log:
                # No industries filter → single DB call → empty → pool is empty
                await agent._discover_companies(_base_state(target_industries=[], target_employee_ranges=[]))

        mock_log.warning.assert_called_once()
        event = mock_log.warning.call_args[0][0]
        assert event == "hr_discovery_agent.empty_company_pool"

    async def test_no_session_guard_sets_failed(self) -> None:
        agent = _make_agent(session=None)
        state = await agent._discover_companies(_base_state())

        assert state["status"] == "failed"
        assert state["discovered_company_ids"] == []
        assert "session" in state["error"].lower()

    async def test_industries_filter_passed_to_repo(self) -> None:
        agent = _make_agent(session=_make_session())
        companies = [_make_company(_COMPANY_A_ID)]
        captured: dict = {}

        async def _capture(**kwargs: object) -> list:
            captured.update(kwargs)
            return companies

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(side_effect=_capture)):
            await agent._discover_companies(_base_state(target_industries=["BFSI", "Insurance"]))

        assert set(captured["industries"]) == {"BFSI", "Insurance"}


# ── TestFindContacts ──────────────────────────────────────────────────────────

class TestFindContacts:
    async def test_fan_out_across_companies_collects_all_contacts(self) -> None:
        agent = _make_agent(session=_make_session())
        contact_a = _make_contact(_CONTACT_A_ID, _COMPANY_A_ID)
        contact_b = _make_contact(_CONTACT_B_ID, _COMPANY_B_ID)

        async def _by_company(company_id: uuid.UUID) -> list:
            if company_id == uuid.UUID(_COMPANY_A_ID):
                return [contact_a]
            return [contact_b]

        with patch.object(HRContactRepo, "find_contactable_by_company", AsyncMock(side_effect=_by_company)):
            state = await agent._find_contacts(
                _base_state(discovered_company_ids=[_COMPANY_A_ID, _COMPANY_B_ID])
            )

        assert set(state["discovered_contact_ids"]) == {_CONTACT_A_ID, _CONTACT_B_ID}

    async def test_deduplication_removes_contact_seen_in_multiple_companies(self) -> None:
        agent = _make_agent(session=_make_session())
        # Same contact returned by both company lookups.
        contact_dup = _make_contact(_CONTACT_A_ID, _COMPANY_A_ID)

        with patch.object(
            HRContactRepo, "find_contactable_by_company", AsyncMock(return_value=[contact_dup])
        ):
            state = await agent._find_contacts(
                _base_state(discovered_company_ids=[_COMPANY_A_ID, _COMPANY_B_ID])
            )

        assert state["discovered_contact_ids"] == [_CONTACT_A_ID]

    async def test_no_contacts_sets_status_completed(self) -> None:
        agent = _make_agent(session=_make_session())

        with patch.object(HRContactRepo, "find_contactable_by_company", AsyncMock(return_value=[])):
            state = await agent._find_contacts(
                _base_state(discovered_company_ids=[_COMPANY_A_ID])
            )

        assert state["discovered_contact_ids"] == []
        assert state["status"] == "completed"


# ── TestQualify ───────────────────────────────────────────────────────────────

class TestQualify:
    async def test_score_filtering_keeps_contacts_at_or_above_threshold(self) -> None:
        agent = _make_agent(session=_make_session())
        ranking = _make_ranking_response([
            (_CONTACT_A_ID, 8),   # above → kept
            (_CONTACT_B_ID, 3),   # below → dropped
            (_CONTACT_C_ID, 5),   # at threshold → kept
        ])

        with patch.object(HRDiscoveryService, "rank_contacts", AsyncMock(return_value=ranking)):
            state = await agent._qualify(
                _base_state(
                    discovered_contact_ids=[_CONTACT_A_ID, _CONTACT_B_ID, _CONTACT_C_ID],
                    qualify_score_threshold=5,
                )
            )

        assert set(state["qualified_contact_ids"]) == {_CONTACT_A_ID, _CONTACT_C_ID}

    async def test_threshold_respected_when_overridden(self) -> None:
        agent = _make_agent(session=_make_session())
        ranking = _make_ranking_response([
            (_CONTACT_A_ID, 7),
            (_CONTACT_B_ID, 4),
        ])

        with patch.object(HRDiscoveryService, "rank_contacts", AsyncMock(return_value=ranking)):
            state = await agent._qualify(
                _base_state(
                    discovered_contact_ids=[_CONTACT_A_ID, _CONTACT_B_ID],
                    qualify_score_threshold=6,
                )
            )

        assert state["qualified_contact_ids"] == [_CONTACT_A_ID]

    async def test_cap_at_50_contacts_sent_to_rank(self) -> None:
        agent = _make_agent(session=_make_session())
        contact_ids = [str(uuid.uuid4()) for _ in range(60)]
        captured_ids: list = []

        async def _capture_rank(req: object) -> MagicMock:
            captured_ids.extend(getattr(req, "contact_ids", []))
            return _make_ranking_response([])

        with patch.object(HRDiscoveryService, "rank_contacts", AsyncMock(side_effect=_capture_rank)):
            await agent._qualify(_base_state(discovered_contact_ids=contact_ids))

        assert len(captured_ids) == 50

    async def test_final_output_contains_all_rankings(self) -> None:
        agent = _make_agent(session=_make_session())
        ranking = _make_ranking_response([(_CONTACT_A_ID, 8), (_CONTACT_B_ID, 3)])

        with patch.object(HRDiscoveryService, "rank_contacts", AsyncMock(return_value=ranking)):
            state = await agent._qualify(
                _base_state(discovered_contact_ids=[_CONTACT_A_ID, _CONTACT_B_ID])
            )

        assert state["final_output"] is not None
        assert "rankings" in state["final_output"]
        # final_output always contains ALL rankings, not just the qualified subset
        assert len(state["final_output"]["rankings"]) == 2

    async def test_rank_contacts_exception_sets_failed(self) -> None:
        agent = _make_agent(session=_make_session())

        with patch.object(
            HRDiscoveryService, "rank_contacts", AsyncMock(side_effect=Exception("LLM timeout"))
        ):
            state = await agent._qualify(
                _base_state(discovered_contact_ids=[_CONTACT_A_ID])
            )

        assert state["status"] == "failed"
        assert "LLM timeout" in state["error"]

    async def test_no_session_guard_sets_failed(self) -> None:
        agent = _make_agent(session=None)
        state = await agent._qualify(
            _base_state(discovered_contact_ids=[_CONTACT_A_ID])
        )

        assert state["status"] == "failed"
        assert "session" in state["error"].lower()


# ── TestFullGraph ─────────────────────────────────────────────────────────────

class TestFullGraph:
    async def test_success_path_populates_all_three_id_lists(self) -> None:
        agent = _make_agent(session=_make_session())
        companies = [_make_company(_COMPANY_A_ID)]
        contacts = [_make_contact(_CONTACT_A_ID, _COMPANY_A_ID)]
        ranking = _make_ranking_response([(_CONTACT_A_ID, 8)])

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(return_value=companies)):
            with patch.object(
                HRContactRepo, "find_contactable_by_company", AsyncMock(return_value=contacts)
            ):
                with patch.object(
                    HRDiscoveryService, "rank_contacts", AsyncMock(return_value=ranking)
                ):
                    state = await agent.run(_base_state(), {})

        assert state["status"] == "completed"
        assert state["discovered_company_ids"] == [_COMPANY_A_ID]
        assert state["discovered_contact_ids"] == [_CONTACT_A_ID]
        assert state["qualified_contact_ids"] == [_CONTACT_A_ID]

    async def test_no_companies_short_circuits_before_find_contacts(self) -> None:
        agent = _make_agent(session=_make_session())

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(return_value=[])):
            with patch.object(
                HRContactRepo, "find_contactable_by_company", AsyncMock()
            ) as mock_find:
                state = await agent.run(_base_state(), {})

        assert state["status"] == "completed"
        assert state["discovered_company_ids"] == []
        mock_find.assert_not_awaited()

    async def test_no_contacts_short_circuits_before_qualify(self) -> None:
        agent = _make_agent(session=_make_session())
        companies = [_make_company(_COMPANY_A_ID)]

        with patch.object(CompanyRepo, "search_by_industries", AsyncMock(return_value=companies)):
            with patch.object(
                HRContactRepo, "find_contactable_by_company", AsyncMock(return_value=[])
            ):
                with patch.object(
                    HRDiscoveryService, "rank_contacts", AsyncMock()
                ) as mock_rank:
                    state = await agent.run(_base_state(), {})

        assert state["status"] == "completed"
        assert state["discovered_contact_ids"] == []
        mock_rank.assert_not_awaited()


# ── TestSmoke ─────────────────────────────────────────────────────────────────

class TestSmoke:
    async def test_qualified_ids_are_subset_of_discovered_and_trainer_profile_flows_through(
        self,
    ) -> None:
        """Full pipeline: trainer niche + target industries → companies → contacts
        → LLM ranking → qualified_contact_ids ⊆ discovered_contact_ids.

        Contact C (score=3) falls below threshold=5 and must NOT appear in
        qualified_contact_ids.  Trainer profile fields must reach rank_contacts.
        """
        agent = _make_agent(session=_make_session())

        company_a = _make_company(_COMPANY_A_ID, industry="BFSI")
        company_b = _make_company(_COMPANY_B_ID, industry="Insurance")
        contact_a = _make_contact(_CONTACT_A_ID, _COMPANY_A_ID)
        contact_b = _make_contact(_CONTACT_B_ID, _COMPANY_B_ID)
        contact_c = _make_contact(_CONTACT_C_ID, _COMPANY_B_ID)

        async def _find_by_company(company_id: uuid.UUID) -> list:
            if company_id == uuid.UUID(_COMPANY_A_ID):
                return [contact_a]
            return [contact_b, contact_c]

        # B=8, A=6, C=3 — only A and B pass threshold=5
        ranking = _make_ranking_response([
            (_CONTACT_B_ID, 8),
            (_CONTACT_A_ID, 6),
            (_CONTACT_C_ID, 3),
        ])

        captured_req: dict = {}

        async def _capture_rank(req: object) -> MagicMock:
            captured_req["trainer_niche"] = getattr(req, "trainer_niche", None)
            captured_req["trainer_topics"] = getattr(req, "trainer_topics", None)
            captured_req["trainer_target_industries"] = getattr(req, "trainer_target_industries", None)
            return ranking

        with patch.object(
            CompanyRepo, "search_by_industries", AsyncMock(return_value=[company_a, company_b])
        ):
            with patch.object(
                HRContactRepo, "find_contactable_by_company", AsyncMock(side_effect=_find_by_company)
            ):
                with patch.object(
                    HRDiscoveryService, "rank_contacts", AsyncMock(side_effect=_capture_rank)
                ):
                    state = await agent.run(
                        _base_state(
                            trainer_niche="Leadership Development",
                            trainer_topics=["Executive Coaching", "Strategic Thinking"],
                            target_industries=["BFSI", "Insurance"],
                            qualify_score_threshold=5,
                        ),
                        {},
                    )

        assert state["status"] == "completed"

        # Qualified must be a proper subset of discovered
        discovered_set = set(state["discovered_contact_ids"])
        qualified_set = set(state["qualified_contact_ids"])
        assert qualified_set.issubset(discovered_set)

        # Contact C (score=3 < threshold=5) must not qualify
        assert _CONTACT_C_ID not in qualified_set
        # Contacts A (score=6) and B (score=8) must qualify
        assert _CONTACT_A_ID in qualified_set
        assert _CONTACT_B_ID in qualified_set

        # Trainer profile flowed into rank_contacts prompt inputs
        assert captured_req["trainer_niche"] == "Leadership Development"
        assert "Executive Coaching" in captured_req["trainer_topics"]
        assert "BFSI" in captured_req["trainer_target_industries"]
