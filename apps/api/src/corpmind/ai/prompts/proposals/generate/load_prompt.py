"""Promptfoo prompt loader for proposals.generate.

Why this exists:
  Our PromptRegistry uses str.format_map() against {variable} placeholders, with
  {{...}} to escape literal braces. Promptfoo defaults to Nunjucks ({{ var }}).
  Loading the markdown file through this Python function guarantees the eval
  sees the EXACT prompt prod sees, byte-for-byte.

Invoked by:
  promptfoo via `prompts: [ "file://load_prompt.py:load" ]` in evals.yaml.

Contract:
  load(context: dict) -> str
  context["vars"] holds the fixture's variable dict.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_FILE = Path(__file__).parent / "v1.md"


def load(context: dict) -> str:
    raw = _PROMPT_FILE.read_text(encoding="utf-8")
    return raw.format_map(context.get("vars", {}))
