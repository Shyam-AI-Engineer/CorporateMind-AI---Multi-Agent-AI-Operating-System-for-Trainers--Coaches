"""OutreachAgent — drafts per-recipient personalized messages with A/B variants.

Sprint 10 implementation: the three TODO nodes are now live.

Graph topology
──────────────
load_context
  └─► generate_variants ──(failed)──► END
        └─► compliance_gate ──(blocked)──► END
              └─► persist_messages ──► END

Node responsibilities
─────────────────────
load_context    — SQL fetch (authoritative) + Qdrant enrichment (non-blocking).
generate_variants — EuriClient call + JSON parse.  Sets status="failed" on bad JSON.
compliance_gate — Delegates to ComplianceGuardAgent (unchanged from stub).
persist_messages — Creates OutboundMessage draft; guards for missing session.

Option A (ADR audit §1.4): the campaign batch path (_run_launch → OutreachService)
is intentionally left untouched.  This agent is an independent path for the
RootOrchestrator and future interactive flows.
"""

from __future__ import annotations

import uuid as _uuid

import structlog
from langgraph.graph import END, StateGraph

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState

log = structlog.get_logger(__name__)


class OutreachAgent(BaseAgent):
    name = "OutreachAgent"

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("load_context", self._load_context)
        graph.add_node("generate_variants", self._generate_variants)
        graph.add_node("compliance_gate", self._compliance_gate)
        graph.add_node("persist_messages", self._persist_messages)

        graph.set_entry_point("load_context")
        graph.add_edge("load_context", "generate_variants")
        # Short-circuit to END when generation fails (bad JSON, missing context).
        graph.add_conditional_edges(
            "generate_variants",
            lambda s: "end" if s.get("status") == "failed" else "compliance",
            {"compliance": "compliance_gate", "end": END},
        )
        graph.add_conditional_edges(
            "compliance_gate",
            lambda s: "persist" if s.get("compliance_outcome") == "allowed" else "end",
            {"persist": "persist_messages", "end": END},
        )
        graph.add_edge("persist_messages", END)

        return graph

    # ── Node implementations ──────────────────────────────────────────────────

    async def _load_context(self, state: AgentState) -> AgentState:
        """Fetch trainer profile (SQL, authoritative) and contact, then enrich
        with a Qdrant similarity score.  Qdrant failures are logged and swallowed
        — they must never block outreach generation.
        """
        from corpmind.ai.trainer_vector_store import TrainerVectorStore  # noqa: PLC0415
        from corpmind.modules.outreach.service import OutreachService  # noqa: PLC0415

        contact_id_str = state.get("contact_id")
        workspace_id_str = state.get("workspace_id")
        tenant_id_str = state.get("tenant_id")

        contact_id = _uuid.UUID(contact_id_str) if contact_id_str else None
        workspace_id = _uuid.UUID(workspace_id_str) if workspace_id_str else None
        tenant_id = _uuid.UUID(tenant_id_str) if tenant_id_str else None

        contact: dict = {}
        trainer: dict = {}

        if self._session is not None:
            svc = OutreachService(self._session)
            if contact_id and tenant_id:
                contact = await svc._fetch_contact(contact_id, tenant_id) or {}
            if workspace_id and tenant_id:
                trainer = await svc._fetch_trainer_profile(workspace_id, tenant_id)

        # Populate authoritative trainer fields into state.
        topics = trainer.get("topics") or []
        state["trainer_context"] = trainer
        state["contact_context"] = contact
        state["trainer_niche"] = trainer.get("niche")
        state["trainer_tone"] = trainer.get("tone")
        state["trainer_topics"] = list(topics) if isinstance(topics, list) else []

        # ── Qdrant enrichment ─────────────────────────────────────────────────
        # Build a richer semantic query from title + company + industry so the
        # embedding is discriminative across HR verticals, not just industry alone.
        qdrant_score = 0.0
        if tenant_id and contact:
            title = contact.get("title") or ""
            company_name = contact.get("company_name") or ""
            industry = contact.get("industry") or ""
            notes = contact.get("notes") or ""
            query = " ".join(p for p in (title, company_name, industry, notes) if p).strip()

            if query:
                store = TrainerVectorStore()
                try:
                    results = await store.search_profiles(
                        query=query, org_id=tenant_id, limit=1
                    )
                    if results:
                        qdrant_score = float(results[0].get("score", 0.0))
                except Exception:
                    log.warning(
                        "outreach_agent.qdrant_unavailable",
                        tenant_id=str(tenant_id),
                        exc_info=True,
                    )
                finally:
                    await store.aclose()

        state["trainer_qdrant_score"] = qdrant_score
        state["last_node"] = "load_context"

        log.info(
            "outreach_agent.context_loaded",
            tenant_id=str(tenant_id) if tenant_id else None,
            contact_id=str(contact_id) if contact_id else None,
            trainer_niche=state.get("trainer_niche"),
            trainer_qdrant_score=qdrant_score,
        )
        return state

    async def _generate_variants(self, state: AgentState) -> AgentState:
        """Build prompt inputs from state, call EuriClient, and parse the copy.

        Sets ``status="failed"`` on JSON parse errors so the graph routes to
        END without attempting compliance or persistence.  Other LLM-layer
        exceptions (rate limit, model unavailable) propagate to BaseAgent.run()
        which handles them at the graph level.
        """
        from corpmind.ai.euri_client import EuriClient  # noqa: PLC0415
        from corpmind.core.exceptions import ValidationError  # noqa: PLC0415
        from corpmind.modules.outreach.service import (  # noqa: PLC0415
            _build_prompt_inputs,
            _parse_outreach_copy,
        )

        trainer = state.get("trainer_context") or {}
        contact = state.get("contact_context") or {}

        if not trainer or not contact:
            state["error"] = "Missing trainer or contact context in state"
            state["status"] = "failed"
            state["last_node"] = "generate_variants"
            return state

        tenant_id_str = state.get("tenant_id") or ""
        request_id = state.get("request_id") or ""

        prompt_inputs = _build_prompt_inputs(contact, trainer)

        llm = EuriClient(session=self._session)
        try:
            result = await llm.chat(
                task="outreach_copy",
                prompt_name="outreach.email",
                prompt_inputs=prompt_inputs,
                tenant_id=_uuid.UUID(tenant_id_str),
                request_id=request_id,
                agent=self.name,
                run_id=state.get("run_id"),
            )
            copy = _parse_outreach_copy(result["content"])
        except ValidationError as exc:
            state["error"] = str(exc)
            state["status"] = "failed"
            state["last_node"] = "generate_variants"
            return state

        state["final_output"] = {
            "subject": copy.get("subject"),
            "body": copy["body"],
            "ab_variant": "A",
        }
        state["last_node"] = "generate_variants"
        return state

    async def _compliance_gate(self, state: AgentState) -> AgentState:
        from corpmind.agents.compliance_guard import ComplianceGuardAgent  # noqa: PLC0415
        guard = ComplianceGuardAgent()
        state = await guard.run(state, {})
        return state

    async def _persist_messages(self, state: AgentState) -> AgentState:
        """Persist the generated draft copy as an OutboundMessage record.

        Requires ``self._session`` — fails explicitly when the agent was
        constructed without one rather than raising an AttributeError.
        """
        from corpmind.modules.outreach.models import OutboundMessage  # noqa: PLC0415
        from corpmind.modules.outreach.repo import OutboundMessageRepo  # noqa: PLC0415

        output = state.get("final_output")
        if not output:
            # No copy generated (e.g. silent skip path) — complete cleanly.
            state["last_node"] = "persist_messages"
            state["status"] = "completed"
            return state

        if self._session is None:
            state["error"] = "No database session — cannot persist outbound message"
            state["status"] = "failed"
            state["last_node"] = "persist_messages"
            return state

        contact_id_str = state.get("contact_id")
        campaign_id_str = state.get("campaign_id")
        channel = state.get("channel") or "email"
        tenant_id_str = state.get("tenant_id")

        if not contact_id_str or not tenant_id_str:
            state["error"] = "Missing contact_id or tenant_id — cannot persist"
            state["status"] = "failed"
            state["last_node"] = "persist_messages"
            return state

        msg = OutboundMessage(
            tenant_id=_uuid.UUID(tenant_id_str),
            campaign_id=_uuid.UUID(campaign_id_str) if campaign_id_str else None,
            contact_id=_uuid.UUID(contact_id_str),
            channel=channel,
            subject=output.get("subject"),
            body=output["body"],
            prompt_version="outreach.email.v1",
            ab_variant=output.get("ab_variant"),
            status="draft",
        )

        repo = OutboundMessageRepo(self._session)
        await repo.create(msg)
        await self._session.commit()

        state["outreach_message_ids"] = [str(msg.id)]
        state["last_node"] = "persist_messages"
        state["status"] = "completed"

        log.info(
            "outreach_agent.message_persisted",
            message_id=str(msg.id),
            contact_id=contact_id_str,
            channel=channel,
            tenant_id=tenant_id_str,
        )
        return state
