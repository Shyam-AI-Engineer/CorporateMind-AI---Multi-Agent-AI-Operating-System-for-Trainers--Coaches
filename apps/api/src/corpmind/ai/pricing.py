"""Per-model token pricing in INR.

Prices are per 1,000 tokens. USD→INR conversion: 83.
Sources: provider pricing pages (May 2026).
Adding a new model to the routing matrix requires updating this table.
"""

from __future__ import annotations

# (input_per_1k_inr, output_per_1k_inr)
_PRICING: dict[str, tuple[float, float]] = {
    # ── Cheap / classification tier ──────────────────────────────────────────
    "deepseek/deepseek-chat":       (0.012, 0.048),    # $0.14/$0.55 per M tokens
    "qwen/qwen2.5-72b":             (0.030, 0.090),    # $0.35/$1.1 per M tokens
    "google/gemini-flash-2.0":      (0.025, 0.075),    # $0.30/$0.9 per M tokens
    "anthropic/claude-haiku-4-5":   (0.021, 0.104),    # $0.25/$1.25 per M tokens

    # ── Premium / copy tier ──────────────────────────────────────────────────
    "anthropic/claude-sonnet-4-6":  (0.249, 1.245),    # $3/$15 per M tokens
    "openai/gpt-4o":                (0.415, 1.245),    # $5/$15 per M tokens
    "openai/gpt-4o-mini":           (0.012, 0.050),    # $0.15/$0.60 per M tokens

    # ── Frontier / planning tier ─────────────────────────────────────────────
    "anthropic/claude-opus-4-7":    (1.245, 6.225),    # $15/$75 per M tokens
}

_FALLBACK_PRICING = (0.083, 0.332)  # conservative estimate when model unknown


def estimate_cost_inr(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return estimated cost in INR for a completed model call."""
    in_rate, out_rate = _PRICING.get(model, _FALLBACK_PRICING)
    return (tokens_in * in_rate + tokens_out * out_rate) / 1_000
