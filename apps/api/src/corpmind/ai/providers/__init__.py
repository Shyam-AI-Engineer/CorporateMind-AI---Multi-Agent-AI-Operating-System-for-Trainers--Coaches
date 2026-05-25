# Provider adapters — the only files allowed to import provider SDKs directly.
# Imports of openai, anthropic, etc. are gated to this package by the
# PreToolUse hook in .claude/scripts/block-direct-llm-imports.sh
