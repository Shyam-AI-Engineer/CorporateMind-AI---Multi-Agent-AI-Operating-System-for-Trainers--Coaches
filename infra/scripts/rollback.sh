#!/usr/bin/env bash
# Emergency rollback script.
# Rolls back to the previous deployment on Railway.
# Alembic downgrade is a SEPARATE manual step — never auto-rolled back.
set -euo pipefail

ENVIRONMENT="${1:-production}"
SERVICE="${2:-api}"

echo "⚠ Rolling back $SERVICE on $ENVIRONMENT..."
echo "⚠ If a migration was applied, downgrade manually FIRST before rolling back."

railway rollback --environment "$ENVIRONMENT" --service "$SERVICE"

echo "✓ Rollback triggered. Verify health at /healthz before continuing."
echo ""
echo "To downgrade migration:"
echo "  railway run --environment $ENVIRONMENT -- python -m alembic downgrade -1"
