"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : app/core/tracing.py

Distributed tracing via OpenTelemetry, exported to Tempo (added to
docker-compose alongside Prometheus/Loki/Grafana - all three signal
types now flow into the same Grafana instance as separate datasources).

Why this matters beyond metrics/logs: metrics tell you THAT something is
slow (e.g. p99 latency on /api/trading/market-order spiked); logs tell
you individual events happened; only a trace tells you WHERE in a single
request's path the time actually went - was it the DB query, the Redis
round-trip to the MT5 worker, or the worker itself. That question comes
up constantly in exactly this kind of system (API -> Redis queue ->
worker -> Redis -> API), which is why this was worth adding rather than
relying on metrics/logs alone.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings
from app.core.logging import configure_logging

logger = configure_logging(__name__)


def setup_tracing(app: FastAPI) -> None:
    if not settings.TRACING_ENABLED:
        logger.info("Tracing disabled (TRACING_ENABLED=False) - set it True and configure OTLP_ENDPOINT to enable.")
        return

    resource = Resource(attributes={SERVICE_NAME: "aegis-api"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.OTLP_ENDPOINT, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()   # covers the payment provider adapters' outbound calls

    logger.info("Tracing enabled - exporting to %s", settings.OTLP_ENDPOINT)
