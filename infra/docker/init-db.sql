-- CorporateMind AI — PostgreSQL initialization for local dev
-- Enables required extensions and sets up RLS infrastructure.

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- for Meilisearch-style text search fallback
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- for JSONB GIN indexes

-- RLS tenant setting (app.tenant_id) is set per-connection by FastAPI middleware.
-- Tables will have: USING (tenant_id = current_setting('app.tenant_id')::uuid)
-- This is configured per-table via Alembic migrations, not here.

-- Create the app user if it doesn't exist (Railway/prod uses DATABASE_URL secrets)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'corpmind') THEN
    CREATE ROLE corpmind LOGIN PASSWORD 'corpmind';
  END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE corpmind_dev TO corpmind;
