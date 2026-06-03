"""FastAPI application factory for CorporateMind AI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration

from corpmind.core.config import settings
from corpmind.core.database import close_db, init_db
from corpmind.core.exceptions import CorporateMindError
from corpmind.core.logging_setup import configure_logging
from corpmind.core.observability import configure_sentry, configure_otel
from corpmind.core.redis import close_redis, init_redis
from corpmind.core.tenancy import TenantMiddleware

log = structlog.get_logger(__name__)


# ── Exception handlers ────────────────────────────────────────────────────────

async def _domain_error_handler(request: Request, exc: CorporateMindError) -> JSONResponse:
    """Translate any CorporateMindError subclass into the structured envelope."""
    request_id = getattr(request.state, "request_id", "")
    log.warning(
        "domain_error",
        code=exc.code,
        http_status=exc.http_status,
        message=exc.message,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "request_id": request_id},
    )


async def _request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Normalize Pydantic request-body validation errors into the same envelope."""
    request_id = getattr(request.state, "request_id", "")
    # Flatten Pydantic's nested error list into a single readable string
    details = "; ".join(
        f"{' → '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    log.warning(
        "request_validation_error",
        details=details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "message": details, "request_id": request_id},
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected exceptions — log with full traceback, return safe envelope."""
    request_id = getattr(request.state, "request_id", "")
    log.exception(
        "unhandled_error",
        exc_type=type(exc).__name__,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "request_id": request_id,
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize and teardown application resources."""
    configure_logging()
    configure_sentry()
    configure_otel()

    await init_db()
    await init_redis()
    log.info("corpmind.startup", env=settings.APP_ENV)

    yield

    await close_redis()
    await close_db()
    log.info("corpmind.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CorporateMind AI",
        version="0.1.0",
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    # ── Middleware (add_middleware prepends, so last-added = outermost) ──────────
    # Execution order on request: TenantMiddleware → CORSMiddleware → app
    # TenantMiddleware bypasses OPTIONS so CORSMiddleware can handle preflights.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.APP_ALLOWED_HOSTS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenantMiddleware)

    # ── Exception handlers ─────────────────────────────────────────────────────
    # Order matters: most-specific first. CorporateMindError before Exception.
    app.add_exception_handler(CorporateMindError, _domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)  # type: ignore[arg-type]

    # ── Prometheus metrics ─────────────────────────────────────────────────────
    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/healthz", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics")

    # ── Routers ────────────────────────────────────────────────────────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    from corpmind.modules.identity.api import router as identity_router
    from corpmind.modules.outreach.api import router as outreach_router
    from corpmind.modules.campaigns.api import router as campaigns_router
    from corpmind.modules.hr_discovery.api import router as hr_router
    from corpmind.modules.analytics.api import router as analytics_router
    from corpmind.modules.proposals.api import router as proposals_router
    from corpmind.modules.crm.api import router as crm_router
    from corpmind.modules.billing.api import router as billing_router
    from corpmind.modules.trainer_intel.api import router as trainer_router
    from corpmind.modules.social.api import router as social_router

    app.include_router(identity_router, prefix="/api/v1/identity", tags=["identity"])
    app.include_router(trainer_router, prefix="/api/v1/trainer", tags=["trainer-intel"])
    app.include_router(hr_router, prefix="/api/v1/hr", tags=["hr-discovery"])
    app.include_router(outreach_router, prefix="/api/v1/outreach", tags=["outreach"])
    app.include_router(campaigns_router, prefix="/api/v1/campaigns", tags=["campaigns"])
    app.include_router(proposals_router, prefix="/api/v1/proposals", tags=["proposals"])
    app.include_router(crm_router, prefix="/api/v1/crm", tags=["crm"])
    app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
    app.include_router(billing_router, prefix="/api/v1/billing", tags=["billing"])
    app.include_router(social_router, prefix="/api/v1/social", tags=["social"])

    # Health check (no auth required)
    from fastapi import APIRouter
    health = APIRouter()

    @health.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(health)

    # Admin routes (platform admin only, separate prefix)
    from corpmind.modules.identity.admin_api import router as admin_router
    app.include_router(admin_router, prefix="/admin/v1", tags=["admin"])


app = create_app()
