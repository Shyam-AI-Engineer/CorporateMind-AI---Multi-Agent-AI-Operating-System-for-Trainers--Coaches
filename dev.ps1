#!/usr/bin/env pwsh
# dev.ps1 — Windows equivalent of the Makefile.
# Usage: ./dev.ps1 <target>
# Run without arguments to see available targets.

param([string]$Target = "help")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root     = $PSScriptRoot
$ApiDir   = Join-Path $Root "apps\api"
$WebDir   = Join-Path $Root "apps\web"
$PkgTypes = Join-Path $Root "packages\shared-types"
$Compose  = Join-Path $Root "infra\docker\compose.dev.yml"

function Invoke-Step([string]$Label, [scriptblock]$Block) {
    Write-Host "`n→ $Label" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Write-Host "✗ $Label failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

switch ($Target) {

    # ── Dependency install ────────────────────────────────────────────────────
    "install" {
        Invoke-Step "Install API deps (uv sync)" {
            Set-Location $ApiDir; uv sync
        }
        Invoke-Step "Install web deps (pnpm install)" {
            Set-Location $WebDir; pnpm install
        }
        Invoke-Step "Install shared-types deps" {
            Set-Location $PkgTypes; pnpm install
        }
        Set-Location $Root
        Write-Host "`n✓ All dependencies installed." -ForegroundColor Green
    }

    # ── Infra (Docker Compose) ────────────────────────────────────────────────
    "infra-up" {
        Invoke-Step "Start Docker Compose services" {
            docker compose -f $Compose up -d
        }
        Write-Host "✓ Postgres, Redis, Qdrant, Meilisearch, Mailhog started." -ForegroundColor Green
    }

    "infra-down" {
        Invoke-Step "Stop Docker Compose services" {
            docker compose -f $Compose down
        }
    }

    "infra-logs" {
        docker compose -f $Compose logs -f
    }

    # ── Migrations ────────────────────────────────────────────────────────────
    "migrate" {
        Invoke-Step "Run Alembic migrations (upgrade head)" {
            Set-Location $ApiDir; uv run alembic upgrade head
        }
        Set-Location $Root
    }

    "migrate-down" {
        Invoke-Step "Downgrade one Alembic revision" {
            Set-Location $ApiDir; uv run alembic downgrade -1
        }
        Set-Location $Root
    }

    "migrate-new" {
        $name = Read-Host "Migration name"
        Invoke-Step "Generate Alembic migration: $name" {
            Set-Location $ApiDir; uv run alembic revision --autogenerate -m $name
        }
        Set-Location $Root
    }

    # ── Linting ───────────────────────────────────────────────────────────────
    "lint-api" {
        Invoke-Step "Ruff lint" {
            Set-Location $ApiDir; uv run ruff check src/ tests/
        }
        Invoke-Step "Mypy type-check" {
            Set-Location $ApiDir; uv run mypy src/
        }
        Set-Location $Root
    }

    "lint-web" {
        Invoke-Step "ESLint" {
            Set-Location $WebDir; pnpm lint
        }
        Invoke-Step "TypeScript check" {
            Set-Location $WebDir; pnpm typecheck
        }
        Set-Location $Root
    }

    "lint" {
        & $PSCommandPath lint-api
        & $PSCommandPath lint-web
    }

    # ── Tests ─────────────────────────────────────────────────────────────────
    "test-api" {
        Invoke-Step "Pytest" {
            Set-Location $ApiDir; uv run pytest -q
        }
        Set-Location $Root
    }

    "test-web" {
        Invoke-Step "Vitest" {
            Set-Location $WebDir; pnpm test
        }
        Set-Location $Root
    }

    "test" {
        & $PSCommandPath test-api
        & $PSCommandPath test-web
    }

    # ── Dev servers (parallel) ────────────────────────────────────────────────
    "dev-api" {
        Set-Location $ApiDir
        uv run uvicorn corpmind.main:app --reload --port 8000
    }

    "dev-worker" {
        Set-Location $ApiDir
        uv run celery -A corpmind.workers.celery_app worker `
            -l info -Q agents,outreach,social,ingestion,analytics,scrape
    }

    "dev-web" {
        Set-Location $WebDir
        pnpm dev
    }

    "dev" {
        # Start infra first, then fan out three processes in separate windows.
        & $PSCommandPath infra-up

        Write-Host "`n→ Launching API, worker, and web in separate terminals..." -ForegroundColor Cyan

        Start-Process pwsh -ArgumentList "-NoExit", "-Command", "& '$PSCommandPath' dev-api"
        Start-Process pwsh -ArgumentList "-NoExit", "-Command", "& '$PSCommandPath' dev-worker"
        Start-Process pwsh -ArgumentList "-NoExit", "-Command", "& '$PSCommandPath' dev-web"

        Write-Host "✓ Three terminals opened. Close them to stop the dev stack." -ForegroundColor Green
    }

    # ── Cleanup ───────────────────────────────────────────────────────────────
    "clean" {
        Write-Host "→ Removing cache directories..." -ForegroundColor Cyan
        $patterns = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next")
        foreach ($p in $patterns) {
            Get-ChildItem -Recurse -Force -Directory -Filter $p -ErrorAction SilentlyContinue |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Host "✓ Clean complete." -ForegroundColor Green
    }

    # ── Help ──────────────────────────────────────────────────────────────────
    default {
        Write-Host @"

CorporateMind AI — dev.ps1 (Windows Makefile equivalent)

Usage:  ./dev.ps1 <target>

Targets:
  install        Install all Python + Node dependencies
  infra-up       Start Postgres, Redis, Qdrant, Meilisearch, Mailhog (Docker)
  infra-down     Stop Docker Compose services
  infra-logs     Tail Docker Compose logs
  migrate        Run Alembic migrations (upgrade head)
  migrate-down   Downgrade one Alembic revision
  migrate-new    Generate a new Alembic migration (interactive)
  lint-api       Ruff + Mypy on apps/api
  lint-web       ESLint + tsc on apps/web
  lint           Both lint-api and lint-web
  test-api       Run pytest
  test-web       Run Vitest
  test           Both test-api and test-web
  dev-api        Start FastAPI dev server (foreground)
  dev-worker     Start Celery worker (foreground)
  dev-web        Start Next.js dev server (foreground)
  dev            Start all three in separate terminal windows
  clean          Remove all build/cache artifacts

"@
    }
}
