"""HRDiscoveryAgent — finds matching companies and opted-in HR contacts.

Sprint 11A implementation: all three nodes are now live.

Graph topology
──────────────
discover_companies ──(no companies)──► END
    └─► find_contacts ──(no contacts)──► END
             └─► qualify ──────────────► END

Node responsibilities
─────────────────────
discover_companies — query tenant's Company table by target industries / employee ranges.
                     Short-circuits to END on empty result.
find_contacts      — asyncio.gather fan-out to HRContactRepo per company; deduplicate by id.
                     Short-circuits to END on empty result.
qualify            — rank via LLM (HRDiscoveryService.rank_contacts); filter by score threshold.

Option A principle (same as OutreachAgent): discovery is an independent path.
RootOrchestrator dispatch and ComplianceGuard are separate sprints — untouched here.
"""

from __future__ import annotations

import asyncio
import uuid as _uuid

import structlog
from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState

log = structlog.get_logger(__name__)


class HRDiscoveryAgent(BaseAgent):
    name = "HRDiscoveryAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("discover_companies", self._discover_companies)
        graph.add_node("find_contacts", self._find_contacts)
        graph.add_node("qualify", self._qualify)

        graph.set_entry_point("discover_companies")

        # Short-circuit to END when no companies match the trainer's targeting criteria.
        graph.add_conditional_edges(
            "discover_companies",
            lambda s: "find_contacts" if s.get("discovered_company_ids") else "end",
            {"find_contacts": "find_contacts", "end": END},
        )
        # Short-circuit to END when no contactable HR contacts exist at the discovered companies.
        graph.add_conditional_edges(
            "find_contacts",
            lambda s: "qualify" if s.get("discovered_contact_ids") else "end",
            {"qualify": "qualify", "end": END},
        )
        graph.add_edge("qualify", END)

        return graph

    # ── Node implementations ──────────────────────────────────────────────────

    async def _discover_companies(self, state: AgentState) -> AgentState:
        """Query the tenant's Company table for companies that match the trainer's
        target industries and employee-count ranges.

        Logs ``hr_discovery_agent.empty_company_pool`` when the tenant has imported
        no companies at all (distinct from "no matches for the filter").
        """
        from corpmind.modules.hr_discovery.repo import CompanyRepo

        tenant_id_str = state.get("tenant_id")

        if self._session is None:
            state["error"] = "No database session — cannot discover companies"
            state["status"] = "failed"
            state["discovered_company_ids"] = []
            state["last_node"] = "discover_companies"
            return state

        industries: list[str] = list(state.get("target_industries") or [])
        employee_ranges: list[str] = list(state.get("target_employee_ranges") or [])

        repo = CompanyRepo(self._session)
        companies = await repo.search_by_industries(
            industries=industries, employee_ranges=employee_ranges
        )

        if not companies:
            # Distinguish "tenant has no data at all" from "filter matched nothing".
            pool_is_empty = True
            if industries or employee_ranges:
                pool = await repo.search_by_industries(
                    industries=[], employee_ranges=[], limit=1
                )
                pool_is_empty = not pool

            if pool_is_empty:
                log.warning(
                    "hr_discovery_agent.empty_company_pool",
                    tenant_id=tenant_id_str,
                )

            state["discovered_company_ids"] = []
            state["status"] = "completed"
            state["last_node"] = "discover_companies"
            return state

        state["discovered_company_ids"] = [str(c.id) for c in companies]
        state["last_node"] = "discover_companies"

        log.info(
            "hr_discovery_agent.companies_discovered",
            tenant_id=tenant_id_str,
            count=len(companies),
            target_industries=industries,
        )
        return state

    async def _find_contacts(self, state: AgentState) -> AgentState:
        """Fan out to HRContactRepo for each discovered company and collect
        all opted-in, deliverable HR contacts.  Contacts appearing under
        multiple companies are deduplicated by ID.
        """
        from corpmind.modules.hr_discovery.repo import HRContactRepo

        tenant_id_str = state.get("tenant_id")

        if self._session is None:
            state["error"] = "No database session — cannot find contacts"
            state["status"] = "failed"
            state["discovered_contact_ids"] = []
            state["last_node"] = "find_contacts"
            return state

        company_id_strs: list[str] = list(state.get("discovered_company_ids") or [])
        company_ids = [_uuid.UUID(cid) for cid in company_id_strs]

        repo = HRContactRepo(self._session)
        batches = await asyncio.gather(
            *[repo.find_contactable_by_company(cid) for cid in company_ids]
        )

        # Flatten and deduplicate — a contact may theoretically be linked to
        # multiple companies if imported more than once.
        seen: set[_uuid.UUID] = set()
        contacts = []
        for batch in batches:
            for c in batch:
                if c.id not in seen:
                    seen.add(c.id)
                    contacts.append(c)

        state["discovered_contact_ids"] = [str(c.id) for c in contacts]
        state["last_node"] = "find_contacts"

        log.info(
            "hr_discovery_agent.contacts_found",
            tenant_id=tenant_id_str,
            count=len(contacts),
            company_count=len(company_ids),
        )

        if not contacts:
            state["status"] = "completed"

        return state

    async def _qualify(self, state: AgentState) -> AgentState:
        """Rank the discovered contacts via LLM and retain only those that
        meet the ``qualify_score_threshold``.

        Exceptions from ``rank_contacts`` (e.g. LLM timeout, empty-contact
        validation error) set ``status="failed"`` and are logged with full
        traceback — they never crash the graph.
        """
        from corpmind.modules.hr_discovery.schemas import RankContactsRequest
        from corpmind.modules.hr_discovery.service import HRDiscoveryService

        tenant_id_str = state.get("tenant_id")

        if self._session is None:
            state["error"] = "No database session — cannot qualify contacts"
            state["status"] = "failed"
            state["last_node"] = "qualify"
            return state

        contact_id_strs: list[str] = list(state.get("discovered_contact_ids") or [])
        # rank_contacts schema caps at 50 contact IDs per call.
        contact_ids = [_uuid.UUID(cid) for cid in contact_id_strs[:50]]

        threshold: int = state.get("qualify_score_threshold") or 5

        req = RankContactsRequest(
            contact_ids=contact_ids,
            trainer_niche=state.get("trainer_niche") or "",
            trainer_topics=list(state.get("trainer_topics") or []),
            trainer_target_industries=list(state.get("target_industries") or []),
        )

        try:
            svc = HRDiscoveryService(self._session)
            ranking_response = await svc.rank_contacts(req)
        except Exception as exc:
            log.error(
                "hr_discovery_agent.qualify_failed",
                tenant_id=tenant_id_str,
                error=str(exc),
                exc_info=True,
            )
            state["error"] = str(exc)
            state["status"] = "failed"
            state["last_node"] = "qualify"
            return state

        qualified = [r for r in ranking_response.rankings if r.score >= threshold]

        state["qualified_contact_ids"] = [str(r.contact_id) for r in qualified]
        state["final_output"] = {
            "rankings": [
                {
                    "contact_id": str(r.contact_id),
                    "score": r.score,
                    "reason": r.reason,
                }
                for r in ranking_response.rankings
            ]
        }
        state["status"] = "completed"
        state["last_node"] = "qualify"

        log.info(
            "hr_discovery_agent.contacts_qualified",
            tenant_id=tenant_id_str,
            count=len(qualified),
            score_threshold=threshold,
        )
        return state
