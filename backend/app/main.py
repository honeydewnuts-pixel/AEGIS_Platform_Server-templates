"""

Project : AEGIS
System : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File : main.py
Version : 3.0.1 - Migrated startup/shutdown from @app.on_event (removed
          in Starlette 1.0+) to the lifespan context manager pattern.

Purpose : FastAPI application entry point.

"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter

from app.config import get_allowed_origins, settings
from app.core.logging import configure_logging
from app.core.startup import on_startup, on_shutdown
from app.core.tracing import setup_tracing

# Routers
from app.api.upload_router import router as upload_router
from app.api.preprocessing_router import router as preprocessing_router
from app.api.chart_detection_router import router as chart_detection_router
from app.api.router import router as base_router
from app.api.trading_router import router as trading_router
from app.api.brain_router import router as brain_router
from app.api.subscription_router import router as subscription_router
from app.api.download_router import router as download_router
from app.api.device_router import router as device_router
from app.api.admin_router import router as admin_router
from app.api.portal_router import router as portal_router
from app.api.signal_router import router as signal_router
from app.api.config_router import router as config_router
from app.api.template_router import router as template_router
from app.api.auth_router import router as auth_router
from app.api.support_router import router as support_router
from app.api.status_router import router as status_router

logger = configure_logging(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Replaces the old @app.on_event("startup"/"shutdown") pair - those
    hooks were removed in Starlette 1.0+ (this codebase upgraded to
    starlette>=1.3.1 to pick up several CVE fixes; see requirements.txt).
    Code before `yield` runs once at startup, code after `yield` runs
    once at shutdown - same two calls as before, just restructured to
    the pattern FastAPI now requires.
    """
    await on_startup(app)
    logger.info("AEGIS API v3.0.1 Started")

    yield

    await on_shutdown(app)
    logger.info("AEGIS API Shut Down")


app = FastAPI(
    title="AEGIS API",
    description="Autonomous Enterprise Global Intelligence System",
    version="3.0.1",
    debug=settings.DEBUG,  # was previously defined in config but never actually wired up
    lifespan=lifespan,
)

# Rate limiting - only actually applied to the checkout endpoint via an
# explicit @limiter.limit(...) decorator (see subscription_router.py and
# app/core/rate_limit.py for the shared Limiter instance). Every other
# endpoint is already gated by API key auth, which is a stronger control
# than IP-based rate limiting; checkout is the one endpoint that's
# deliberately unauthenticated (a brand-new subscriber has no key yet),
# which is exactly what makes it the one worth limiting.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

setup_tracing(app)

# CORS - explicit origin allowlist required. "*" + credentials is both
# rejected by browsers and unsafe, so it's deliberately not supported here.
origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# INCLUDE ALL ROUTERS
# ==========================================================

app.include_router(template_router)
app.include_router(auth_router)
app.include_router(support_router)
app.include_router(status_router)
app.include_router(base_router)
app.include_router(upload_router)
app.include_router(preprocessing_router)
app.include_router(chart_detection_router)
app.include_router(trading_router)
app.include_router(brain_router)
app.include_router(subscription_router)
app.include_router(download_router)
app.include_router(device_router)
app.include_router(admin_router)
app.include_router(portal_router)
app.include_router(signal_router)
app.include_router(config_router)

# /metrics - HTTP request counts/latencies auto-instrumented, plus custom
# business gauges from app.core.metrics (populated by a background loop
# started in on_startup). Put behind your reverse proxy / firewall in
# production - this isn't behind verify_api_key, matching how Prometheus
# scraping conventionally works (network-level access control instead).
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Static frontends - served directly by this app so there's nothing
# extra to deploy. Mounted last so they don't shadow any API route.
_frontend_root = Path(__file__).resolve().parents[2]  # repo root
admin_dir = _frontend_root / "admin_dashboard"
portal_dir = _frontend_root / "client_portal"
if admin_dir.exists():
    app.mount("/admin", StaticFiles(directory=str(admin_dir), html=True), name="admin_dashboard")
if portal_dir.exists():
    app.mount("/portal", StaticFiles(directory=str(portal_dir), html=True), name="client_portal")


@app.get("/")
async def root():
    return {
        "service": "AEGIS API",
        "version": "3.0.1",
        "status": "online",
        "modules": ["upload", "preprocessing", "chart_detection", "trading", "brain", "subscriptions", "download", "devices", "admin", "portal"],
    }


@app.get("/health")
async def health(request: Request):
    """
    Liveness + shallow dependency check for Render / load balancers.
    Returns 200 when the process is up and Redis responds to PING.
    Does not require an API key so external pingers can keep free-tier
    instances warm and so healthCheckPath can be pointed here if desired.
    """
    redis_ok = False
    try:
        job_queue = getattr(request.app.state, "job_queue", None)
        if job_queue is not None:
            client = job_queue.get_redis_client()
            if client is not None:
                await client.ping()
                redis_ok = True
    except Exception:  # noqa: BLE001
        redis_ok = False

    status = "ok" if redis_ok else "degraded"
    code = 200 if redis_ok else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "redis": redis_ok,
            "service": "AEGIS API",
            "version": "3.0.1",
        },
    )
