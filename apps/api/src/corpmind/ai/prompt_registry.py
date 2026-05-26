"""File-based versioned prompt registry.

Prompts live in: apps/api/src/corpmind/ai/prompts/<name>/v<N>.md
The registry loads the highest available version for each prompt name.
Template substitution uses Python str.format_map() against prompt_inputs.

Usage:
    registry = PromptRegistry()
    prompt_text, version = registry.load("outreach.email", {"recipient_name": "Alice"})
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_VERSION_RE = re.compile(r"^v(\d+)\.md$")


class PromptRegistry:
    """Resolves prompt name → versioned markdown file → rendered string."""

    def load(
        self,
        prompt_name: str,
        inputs: dict[str, Any],
        version: int | None = None,
    ) -> tuple[str, str]:
        """Load and render a prompt.

        Args:
            prompt_name: Dot-separated name, e.g. "outreach.email".
            inputs: Template substitution values (used with str.format_map).
            version: Pin to a specific version; None = latest.

        Returns:
            (rendered_prompt_text, version_string) e.g. ("Dear {name}...", "v3")
        """
        prompt_dir = _PROMPTS_DIR / prompt_name.replace(".", "/")

        if not prompt_dir.exists():
            log.warning("prompt_registry.missing", prompt_name=prompt_name)
            return self._fallback(inputs), "fallback"

        resolved_version, path = self._resolve(prompt_dir, version)
        if path is None:
            log.warning("prompt_registry.no_versions", prompt_name=prompt_name)
            return self._fallback(inputs), "fallback"

        raw = path.read_text(encoding="utf-8")
        try:
            rendered = raw.format_map(inputs)
        except KeyError as exc:
            log.warning("prompt_registry.missing_input", prompt_name=prompt_name, key=str(exc))
            rendered = raw  # send unrendered rather than crashing

        log.debug("prompt_registry.loaded", prompt_name=prompt_name, version=resolved_version)
        return rendered, resolved_version

    def _resolve(self, prompt_dir: Path, version: int | None) -> tuple[str, Path | None]:
        versions: list[tuple[int, Path]] = []
        for f in prompt_dir.iterdir():
            m = _VERSION_RE.match(f.name)
            if m:
                versions.append((int(m.group(1)), f))

        if not versions:
            return "none", None

        if version is not None:
            for n, path in versions:
                if n == version:
                    return f"v{n}", path
            return "none", None

        best_n, best_path = max(versions, key=lambda t: t[0])
        return f"v{best_n}", best_path

    def _fallback(self, inputs: dict[str, Any]) -> str:
        """When no prompt file exists, format inputs as a minimal user message."""
        return "\n".join(f"{k}: {v}" for k, v in inputs.items())


# Module-level singleton — loaded once per worker process.
registry = PromptRegistry()
