"""ReplyClassifierAgent — assigns a business intent to an inbound email reply.

Single-purpose, side-effect-free LLM agent.  The graph has one classify node
that calls EuriClient with task="classify_reply" (cheap-model chain) and
returns a strict-schema ClassificationResult.

The worker that drives reply persistence (workers/tasks/inbox.py) invokes
classify() directly — bypassing the LangGraph compile/invoke overhead — because
the agent has no fan-out, no HITL, no checkpointing.  build_graph() exists to
keep the agent introspectable from the agent registry (parity with the other 14
agents) and to enable replay debugging via the standard runner.

Failure isolation:
  - Malformed JSON, missing keys, unrecognised labels → coerced to "unknown".
  - Underlying EuriClient errors propagate; the worker is responsible for
    catching them so message persistence still succeeds.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Literal

import structlog
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field, ValidationError

from corpmind.agents.base import BaseAgent
from corpmind.agents.state import AgentState
from corpmind.ai.euri_client import EuriClient

log = structlog.get_logger(__name__)


ReplyIntent = Literal[
    "interested",
    "not_interested",
    "question",
    "out_of_office",
    "bounce",
    "auto_reply",
    "unsubscribe",
    "unknown",
]

_ALLOWED_INTENTS: frozenset[str] = frozenset(
    {
        "interested",
        "not_interested",
        "question",
        "out_of_office",
        "bounce",
        "auto_reply",
        "unsubscribe",
        "unknown",
    }
)

# Greedy JSON-object extractor — pulls the first {...} block out of the model
# output.  Tolerates the model wrapping the answer in markdown fences or prose
# even though the prompt forbids it.
_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


class ClassificationResult(BaseModel):
    """Strict-schema output returned to the worker.

    `model_name` echoes whichever model in the fallback chain actually served
    the request (recorded in model_runs by EuriClient; we mirror it here for
    inbox_messages.classification_model).
    """

    intent: ReplyIntent
    confidence: float = Field(ge=0.0, le=1.0)
    model_name: str


def _coerce_unknown(model_name: str) -> ClassificationResult:
    """Safe fallback when the model output cannot be trusted."""
    return ClassificationResult(intent="unknown", confidence=0.0, model_name=model_name)


def _parse_model_output(raw: str, model_name: str) -> ClassificationResult:
    """Extract intent + confidence from a (possibly noisy) LLM response.

    Defense-in-depth ordering:
      1. Try a JSON parse on the first {...} block.
      2. Validate intent against the allowlist; unknown labels → "unknown".
      3. Clamp confidence to [0.0, 1.0]; missing → 0.0.

    Returns a "unknown"/0.0 result if any step fails — never raises.
    """
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return _coerce_unknown(model_name)

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _coerce_unknown(model_name)

    if not isinstance(data, dict):
        return _coerce_unknown(model_name)

    intent_raw = str(data.get("intent", "unknown")).strip().lower()
    if intent_raw not in _ALLOWED_INTENTS:
        intent_raw = "unknown"

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    try:
        return ClassificationResult(
            intent=intent_raw,  # type: ignore[arg-type]
            confidence=confidence,
            model_name=model_name,
        )
    except ValidationError:
        return _coerce_unknown(model_name)


class ReplyClassifierAgent(BaseAgent):
    """Classifies an inbound email into a single business intent label.

    Tools: none.  The agent is a single LLM call with deterministic parsing.
    Read-only: it returns a ClassificationResult; persistence is the worker's
    responsibility.  Cost class: classify_reply (cheap chain — see routing.py).
    """

    name = "ReplyClassifierAgent"

    def __init__(self, euri: EuriClient) -> None:
        self._euri = euri

    def build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("classify", self._classify_node)
        graph.set_entry_point("classify")
        graph.add_edge("classify", END)
        return graph

    async def _classify_node(self, state: AgentState) -> AgentState:
        """Graph-node adapter — pulls inputs from AgentState and writes back."""
        state["last_node"] = "classify"
        return state

    async def classify(
        self,
        *,
        subject: str | None,
        body_snippet: str | None,
        from_address: str,
        campaign_context: str | None,
        tenant_id: uuid.UUID,
        request_id: str,
        run_id: str | None = None,
        prompt_name: str = "inbox.classify_reply",
    ) -> ClassificationResult:
        """Classify a single inbound reply.

        Args:
            subject: Email subject line. None / empty is allowed.
            body_snippet: First ~500 chars of plain-text body. Decrypted by caller.
            from_address: Sender's email address (used as a heuristic signal in
                the prompt — bounce notifications come from MAILER-DAEMON, etc.).
            campaign_context: Optional context from the matched outbound campaign;
                empty string when no outbound match exists.
            tenant_id: Required for EuriClient budget tracking + tracing.
            request_id: Correlation ID propagated from the sync task.
            run_id: Optional workflow run ID (for Langfuse span linking).

        Returns:
            ClassificationResult — never raises on parse failure (falls back to
            "unknown" / 0.0). Underlying EuriClient errors (BudgetExceededError,
            ModelUnavailableError) DO propagate; the worker must catch them.
        """
        response = await self._euri.chat(
            task="classify_reply",
            prompt_name=prompt_name,
            prompt_inputs={
                "subject": subject or "",
                "body_snippet": (body_snippet or "")[:500],
                "from_address": from_address,
                "campaign_context": campaign_context or "",
            },
            tenant_id=tenant_id,
            request_id=request_id,
            agent=self.name,
            run_id=run_id,
        )

        raw_text = str(response.get("content", ""))
        # EuriClient does not surface the actual model used in its return value
        # today; fall back to the routing chain's primary if the gateway omits it.
        model_name = str(response.get("model", "gpt-4.1-nano"))

        result = _parse_model_output(raw_text, model_name)

        log.info(
            "reply_classifier.complete",
            intent=result.intent,
            confidence=round(result.confidence, 3),
            model=result.model_name,
            tenant_id=str(tenant_id),
            request_id=request_id,
        )
        return result
