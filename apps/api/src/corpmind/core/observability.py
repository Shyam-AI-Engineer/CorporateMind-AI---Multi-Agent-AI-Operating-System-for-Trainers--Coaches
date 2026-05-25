"""Observability initialization: Sentry + OpenTelemetry."""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def configure_sentry() -> None:
    from corpmind.core.config import settings

    if not settings.SENTRY_DSN:
        log.info("sentry.skipped", reason="SENTRY_DSN not set")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        integrations=[
            FastApiIntegration(transaction_style="url"),
            CeleryIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        send_default_pii=False,
    )
    log.info("sentry.initialized", env=settings.APP_ENV)


def configure_otel() -> None:
    from corpmind.core.config import settings

    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        log.info("otel.initialized")
    except ImportError:
        log.warning("otel.skipped", reason="opentelemetry packages not installed")
