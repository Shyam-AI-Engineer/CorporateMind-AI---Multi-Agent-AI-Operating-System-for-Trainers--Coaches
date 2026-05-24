#!/usr/bin/env bash
# Runs after every Edit/Write. Permissive (|| true) so it never blocks the edit.
# Use a stricter pre-push gate (CI) for hard enforcement.
set -e

echo "→ CorporateMind AI: post-edit checks"

if [ -d "apps/api" ] && [ -f "apps/api/pyproject.toml" ]; then
  pushd apps/api >/dev/null
  command -v ruff   >/dev/null 2>&1 && { echo "  ruff check";   ruff check .   || true; }
  command -v mypy   >/dev/null 2>&1 && { echo "  mypy src";     mypy src       || true; }
  command -v pytest >/dev/null 2>&1 && { echo "  pytest -q";    pytest -q      || true; }
  popd >/dev/null
fi

if [ -d "apps/web" ] && [ -f "apps/web/package.json" ]; then
  pushd apps/web >/dev/null
  command -v npm >/dev/null 2>&1 && {
    echo "  web: lint";      npm run -s lint      2>/dev/null || true
    echo "  web: typecheck"; npm run -s typecheck 2>/dev/null || true
  }
  popd >/dev/null
fi

echo "✓ post-edit checks complete"
