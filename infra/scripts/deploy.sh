#!/usr/bin/env bash
# CorporateMind AI deploy script — used by GitHub Actions CI.
# Triggers Railway canary deploy; Vercel deploys automatically on main push.
set -euo pipefail

ENVIRONMENT="${1:-staging}"

echo "→ Deploying to $ENVIRONMENT..."

if [[ "$ENVIRONMENT" == "production" ]]; then
  echo "→ Verifying staging soak (requires manual confirmation in CI)"
fi

# Run database migrations before deploying the API
echo "→ Running Alembic migrations..."
railway run --environment "$ENVIRONMENT" -- python -m alembic upgrade head

# Deploy API container
echo "→ Deploying API service..."
railway up --environment "$ENVIRONMENT" --service api --detach

# Deploy Celery workers
echo "→ Deploying Celery workers..."
railway up --environment "$ENVIRONMENT" --service worker --detach

echo "✓ Deploy triggered for $ENVIRONMENT. Monitor at Railway dashboard."
