"""LLM model routing matrix.

Maps task classes to (primary, fallback_chain) model lists.
Adding a new task class requires an ADR (see adr.md).

Model IDs use Euri gateway naming (no provider prefix):
- Cheap: gpt-4.1-nano, gemini-2.5-flash, claude-haiku-4-5
- Premium: claude-sonnet-4-6, claude-opus-4-7, gpt-4.1
"""

from __future__ import annotations

_ROUTING_MATRIX: dict[str, list[str]] = {
    # ── Classification / Extraction (cheap) ───────────────────────────────────
    "classify_intent":      ["gpt-4.1-nano", "gemini-2.5-flash", "claude-haiku-4-5"],
    "extract_fields":       ["gpt-4.1-nano", "gemini-2.5-flash", "claude-haiku-4-5"],
    "classify_reply":       ["gpt-4.1-nano", "gemini-2.5-flash", "claude-haiku-4-5"],
    "detect_sentiment":     ["gpt-4.1-nano", "gemini-2.5-flash"],
    "tag_content":          ["gpt-4.1-nano", "gemini-2.5-flash"],
    "rank_contacts":        ["gpt-4.1-nano", "gemini-2.5-flash"],
    "detect_duplicates":    ["gpt-4.1-nano", "gemini-2.5-flash"],

    # ── Personalized copy (premium) ───────────────────────────────────────────
    "outreach_copy":        ["claude-sonnet-4-6", "gpt-4.1", "claude-haiku-4-5"],
    "proposal_generation":  ["claude-opus-4-7", "claude-sonnet-4-6", "gpt-4.1"],
    "viral_hooks":          ["claude-sonnet-4-6", "gpt-4.1"],
    "social_post":          ["claude-sonnet-4-6", "gpt-4.1-mini"],
    "trainer_extraction":   ["claude-sonnet-4-6", "gpt-4.1-mini"],

    # ── Planning (premium) ────────────────────────────────────────────────────
    "root_planning":        ["claude-opus-4-7", "claude-sonnet-4-6"],
}

_DEFAULT_CHAIN = ["gpt-4.1-nano", "gemini-2.5-flash"]


def get_model_chain(task: str) -> list[str]:
    """Return the ordered model fallback chain for a given task class."""
    return _ROUTING_MATRIX.get(task, _DEFAULT_CHAIN)
