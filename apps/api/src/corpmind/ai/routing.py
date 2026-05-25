"""LLM model routing matrix.

Maps task classes to (primary, fallback_chain) model lists.
Adding a new task class requires an ADR (see adr.md).

Cost tiers:
- Cheap: DeepSeek, Qwen, Gemini Flash, Haiku, Phi
- Premium: Claude Sonnet/Opus, GPT-4-class
"""

from __future__ import annotations

_ROUTING_MATRIX: dict[str, list[str]] = {
    # ── Classification / Extraction (cheap) ───────────────────────────────────
    "classify_intent":      ["deepseek/deepseek-chat", "anthropic/claude-haiku-4-5", "google/gemini-flash-2.0"],
    "extract_fields":       ["deepseek/deepseek-chat", "qwen/qwen2.5-72b", "anthropic/claude-haiku-4-5"],
    "classify_reply":       ["deepseek/deepseek-chat", "anthropic/claude-haiku-4-5", "google/gemini-flash-2.0"],
    "detect_sentiment":     ["deepseek/deepseek-chat", "anthropic/claude-haiku-4-5"],
    "tag_content":          ["deepseek/deepseek-chat", "qwen/qwen2.5-72b"],
    "rank_contacts":        ["deepseek/deepseek-chat", "anthropic/claude-haiku-4-5"],
    "detect_duplicates":    ["deepseek/deepseek-chat", "qwen/qwen2.5-72b"],

    # ── Personalized copy (premium) ───────────────────────────────────────────
    "outreach_copy":        ["anthropic/claude-sonnet-4-6", "openai/gpt-4o", "anthropic/claude-haiku-4-5"],
    "proposal_generation":  ["anthropic/claude-opus-4-7", "anthropic/claude-sonnet-4-6", "openai/gpt-4o"],
    "viral_hooks":          ["anthropic/claude-sonnet-4-6", "openai/gpt-4o"],
    "social_post":          ["anthropic/claude-sonnet-4-6", "deepseek/deepseek-chat"],
    "trainer_extraction":   ["anthropic/claude-sonnet-4-6", "openai/gpt-4o-mini"],

    # ── Planning (premium) ───────────────────────────────────────────────────
    "root_planning":        ["anthropic/claude-opus-4-7", "anthropic/claude-sonnet-4-6"],
}

_DEFAULT_CHAIN = ["deepseek/deepseek-chat", "anthropic/claude-haiku-4-5"]


def get_model_chain(task: str) -> list[str]:
    """Return the ordered model fallback chain for a given task class."""
    return _ROUTING_MATRIX.get(task, _DEFAULT_CHAIN)
