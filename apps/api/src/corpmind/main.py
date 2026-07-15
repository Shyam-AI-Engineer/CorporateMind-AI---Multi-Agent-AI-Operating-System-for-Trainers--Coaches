"""FastAPI application factory for CorporateMind AI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
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
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
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
        version="1.0.0",
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    # ── Middleware (add_middleware prepends, so last-added = outermost) ──────────
    # Execution order on request: TenantMiddleware → CORSMiddleware → app
    # TenantMiddleware bypasses OPTIONS so CORSMiddleware can handle preflights.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.APP_ALLOWED_HOSTS),
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
    from corpmind.modules.crm.api import lead_pipeline_router
    from corpmind.modules.billing.api import router as billing_router
    from corpmind.modules.billing.api import customer_invoice_router
    from corpmind.modules.trainer_intel.api import router as trainer_router
    from corpmind.modules.social.api import router as social_router

    from corpmind.modules.inbox.api import router as inbox_router
    from corpmind.modules.crm.booking_webhook import router as booking_webhook_router
    from corpmind.modules.whatsapp.api import router as whatsapp_router
    from corpmind.modules.dashboard.api import router as dashboard_router
    from corpmind.modules.operations.api import router as operations_router
    from corpmind.modules.team.api import router as team_router
    from corpmind.modules.approvals.api import router as approvals_router
    from corpmind.modules.notifications.api import router as notifications_router
    from corpmind.modules.workflows.api import router as workflows_router
    from corpmind.modules.workflows.api import steps_router as workflow_steps_router
    from corpmind.modules.workflows.api import run_router as workflow_runs_router
    from corpmind.modules.workflows.api import run_steps_router as workflow_run_steps_router
    from corpmind.modules.workflows.api import analytics_router as workflow_analytics_router
    from corpmind.modules.workflows.api import sla_router as workflow_sla_router
    from corpmind.modules.workflows.api import effectiveness_router as workflow_effectiveness_router
    from corpmind.modules.workflows.api import observability_router as workflow_observability_router
    from corpmind.modules.customers.api import router as customers_router
    from corpmind.modules.customer_success.api import router as customer_success_router
    from corpmind.modules.customer_success.api import customer_success_router as customers_success_sub_router
    from corpmind.modules.customer_renewals.api import router as customer_renewals_router
    from corpmind.modules.customer_renewals.api import customer_renewal_router as customers_renewal_sub_router
    from corpmind.modules.customer_success.timeline_api import router as customer_timeline_router
    from corpmind.modules.training.api import router as training_router
    from corpmind.modules.training.api import sessions_router as training_sessions_router
    from corpmind.modules.training.api import attendance_router as training_attendance_router
    from corpmind.modules.training.api import certificates_router as training_certificates_router
    from corpmind.modules.training.api import feedback_router as training_feedback_router
    from corpmind.modules.training.api import customers_feedback_router as training_customers_feedback_router
    from corpmind.modules.training.api import trainers_feedback_router as training_trainers_feedback_router
    from corpmind.modules.executive_dashboard.api import router as executive_dashboard_router
    from corpmind.modules.audit.api import router as audit_router
    from corpmind.modules.admin.api import router as admin_router
    from corpmind.modules.integrations.api import router as integrations_router
    from corpmind.modules.reporting.api import router as reporting_router
    from corpmind.modules.observability.api import router as observability_router
    from corpmind.modules.security.api import router as security_router
    from corpmind.modules.bulk_operations.api import router as bulk_operations_router

    app.include_router(identity_router, prefix="/api/v1/identity", tags=["identity"])
    app.include_router(inbox_router, prefix="/api/v1/inbox", tags=["inbox"])
    app.include_router(trainer_router, prefix="/api/v1/trainer", tags=["trainer-intel"])
    app.include_router(hr_router, prefix="/api/v1/hr", tags=["hr-discovery"])
    app.include_router(outreach_router, prefix="/api/v1/outreach", tags=["outreach"])
    app.include_router(campaigns_router, prefix="/api/v1/campaigns", tags=["campaigns"])
    app.include_router(proposals_router, prefix="/api/v1/proposals", tags=["proposals"])
    app.include_router(crm_router, prefix="/api/v1/crm", tags=["crm"])
    app.include_router(lead_pipeline_router, prefix="/api/v1/lead-pipeline", tags=["lead-pipeline"])
    app.include_router(customers_router, prefix="/api/v1/customers", tags=["customers"])
    app.include_router(customer_success_router, prefix="/api/v1/customer-success", tags=["customer-success"])
    app.include_router(customers_success_sub_router, prefix="/api/v1/customers", tags=["customer-success"])
    app.include_router(customer_renewals_router, prefix="/api/v1/customer-renewals", tags=["customer-renewals"])
    app.include_router(customers_renewal_sub_router, prefix="/api/v1/customers", tags=["customer-renewals"])
    app.include_router(customer_timeline_router, prefix="/api/v1", tags=["customer-360"])
    app.include_router(training_router, prefix="/api/v1/training-engagements", tags=["training"])
    app.include_router(training_sessions_router, prefix="/api/v1/training-sessions", tags=["training"])
    app.include_router(training_attendance_router, prefix="/api/v1/training-attendance", tags=["training"])
    app.include_router(training_certificates_router, prefix="/api/v1/training-certificates", tags=["training"])
    app.include_router(training_feedback_router, prefix="/api/v1/training-feedback", tags=["training"])
    app.include_router(training_customers_feedback_router, prefix="/api/v1/customers", tags=["training"])
    app.include_router(training_trainers_feedback_router, prefix="/api/v1/trainers", tags=["training"])
    app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
    app.include_router(billing_router, prefix="/api/v1/billing", tags=["billing"])
    app.include_router(customer_invoice_router, prefix="/api/v1/customers", tags=["billing"])
    app.include_router(social_router, prefix="/api/v1/social", tags=["social"])
    app.include_router(booking_webhook_router, prefix="/api/v1/webhooks", tags=["webhooks"])
    app.include_router(whatsapp_router, prefix="/api/v1/whatsapp", tags=["whatsapp"])
    app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["dashboard"])
    app.include_router(operations_router, prefix="/api/v1/operations", tags=["operations"])
    app.include_router(team_router, prefix="/api/v1/team", tags=["team"])
    app.include_router(approvals_router, prefix="/api/v1/approvals", tags=["approvals"])
    app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["notifications"])
    app.include_router(workflows_router, prefix="/api/v1/workflow-templates", tags=["workflows"])
    app.include_router(workflow_steps_router, prefix="/api/v1/workflow-steps", tags=["workflows"])
    app.include_router(workflow_runs_router, prefix="/api/v1/workflow-runs", tags=["workflow-runs"])
    app.include_router(workflow_run_steps_router, prefix="/api/v1/workflow-run-steps", tags=["workflow-runs"])
    app.include_router(workflow_analytics_router, prefix="/api/v1/workflow-analytics", tags=["workflow-analytics"])
    app.include_router(workflow_sla_router, prefix="/api/v1/workflow-sla", tags=["workflow-sla"])
    app.include_router(workflow_effectiveness_router, prefix="/api/v1/workflow-effectiveness", tags=["workflow-effectiveness"])
    app.include_router(workflow_observability_router, prefix="/api/v1/workflow-observability", tags=["workflow-observability"])
    app.include_router(executive_dashboard_router, prefix="/api/v1/executive-dashboard", tags=["executive-dashboard"])
    app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(integrations_router, prefix="/api/v1/integrations", tags=["integrations"])
    app.include_router(reporting_router, prefix="/api/v1/reports", tags=["reporting"])
    app.include_router(observability_router, prefix="/api/v1/observability", tags=["observability"])
    app.include_router(security_router, prefix="/api/v1/security", tags=["security"])
    app.include_router(bulk_operations_router, prefix="/api/v1/bulk", tags=["bulk-operations"])

    # Health check (no auth required)
    from corpmind.core.health import healthz_handler
    from fastapi import APIRouter
    health = APIRouter()
    health.add_api_route("/healthz", healthz_handler, methods=["GET"], include_in_schema=False)
    app.include_router(health)

    # Admin routes (platform admin only, separate prefix)
    from corpmind.modules.identity.admin_api import router as platform_admin_router
    app.include_router(platform_admin_router, prefix="/admin/v1", tags=["platform-admin"])


app = create_app()
