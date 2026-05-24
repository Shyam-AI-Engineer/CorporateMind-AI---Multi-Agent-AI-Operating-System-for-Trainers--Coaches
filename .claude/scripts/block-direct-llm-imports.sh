#!/usr/bin/env bash
# PreToolUse guard: blocks direct LLM-provider SDK imports inside apps/api/.
# Enforces the "Euri AI Gateway is the sole LLM egress" rule mechanically.
#
# Reads the Edit/Write tool input from stdin (JSON). If the target file is under
# apps/api/ and the proposed content imports openai / anthropic / google.generativeai
# / cohere / mistralai directly, exits non-zero with a pointer to the rule file.
#
# Exception path: anything under apps/api/src/corpmind/ai/euri_client.py is allowed
# to import providers (that's the gateway's internal implementation).

set -e

PAYLOAD="$(cat)"
FILE_PATH=$(printf '%s' "$PAYLOAD" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")
CONTENT=$(printf '%s' "$PAYLOAD" | python -c "import sys,json; d=json.load(sys.stdin); ti=d.get('tool_input',{}); print(ti.get('content','') or ti.get('new_string',''))" 2>/dev/null || echo "")

# Only enforce inside backend
case "$FILE_PATH" in
  *apps/api/* ) ;;
  * ) exit 0 ;;
esac

# Allowlist: the EuriClient itself may import providers
case "$FILE_PATH" in
  *apps/api/src/corpmind/ai/euri_client.py ) exit 0 ;;
  *apps/api/src/corpmind/ai/providers/*    ) exit 0 ;;
esac

BANNED='^[[:space:]]*(from|import)[[:space:]]+(openai|anthropic|google\.generativeai|cohere|mistralai|litellm)([[:space:]]|$|\.)'

if printf '%s' "$CONTENT" | grep -Eq "$BANNED"; then
  cat >&2 <<'MSG'
✗ Direct LLM-provider SDK import blocked.

CorporateMind AI routes ALL LLM calls through corpmind.ai.euri_client.EuriClient.
Direct imports of openai / anthropic / google.generativeai / cohere / mistralai
are forbidden in business modules.

  - Use: from corpmind.ai.euri_client import EuriClient
  - See: .claude/rules/euri-gateway.md

If you genuinely need to extend the gateway itself, put your code in
apps/api/src/corpmind/ai/ — that path is allowlisted.
MSG
  exit 2
fi

exit 0
