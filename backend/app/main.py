"""
SphinxGate — FastAPI application entry point.

Phase 4 additions:
  - Fault injection router mounted at /api/v1/faults/*
  - Incident management router mounted at /api/v1/incidents/*
  - Fault-aware provider resolver installed at startup (when enabled)
  - Incident detector singleton initialized at startup
  - Version bumped to 0.4.0
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.gateway.router import router as gateway_router
from app.gateway.telemetry_router import router as telemetry_router
from app.gateway.fault_router import router as fault_router
from app.gateway.incident_router import router as incident_router

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sphinxgate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Phase 3: Telemetry store ───────────────────────────────────────────────
    from app.telemetry.store import get_telemetry_store
    store = get_telemetry_store()
    await store.initialize()

    # ── Phase 4a: Fault injection provider resolver ────────────────────────────
    # When FAULT_INJECTION_ENABLED=true, replace the engine's provider resolver
    # with a fault-aware version.  The engine imports get_provider from
    # app.providers.registry — we patch that module-level name so the engine
    # picks up fault-aware providers transparently without any engine changes.
    from app.fault_injection.store import is_fault_injection_enabled, get_fault_store
    if is_fault_injection_enabled():
        import app.providers.registry as registry_module
        from app.fault_injection.resolver import make_fault_aware_resolver
        registry_module.get_provider = make_fault_aware_resolver(get_fault_store())
        logger.warning(
            "⚡ FAULT INJECTION ENABLED — provider resolver patched. "
            "THIS IS A DEVELOPMENT/DEMO ENVIRONMENT."
        )
    else:
        logger.info("Fault injection: DISABLED (FAULT_INJECTION_ENABLED not set)")

    # ── Phase 4b: Incident detector ────────────────────────────────────────────
    from app.incidents.detector import get_incident_detector
    get_incident_detector()   # Initialize singleton
    logger.info("Incident detector initialized")

    # ── Phase 5: Active Health Checker ─────────────────────────────────────────
    from app.health.checker import get_health_checker
    checker = get_health_checker()
    checker.start()
    logger.info("Active Health Checker started")

    logger.info("SphinxGate v0.5.0 started — Facade + Telemetry + Cache + Fault Injection + Incidents + Active Health")
    yield
    await checker.stop()


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SphinxGate",
    description="AI API Gateway — Phase 4 (Fault Injection + Incident Management)",
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

settings = get_settings()


# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-Provider",
        "X-Latency-Ms",
        "X-Retry-Count",
        "X-Circuit-State",
        "X-Tokens-Used",
        "X-Fallback-Used",
        "X-Cache-Hit",
        "X-Fault-Id",       # Phase 4: fault injection tracing
    ],
)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health():
    """Simple liveness endpoint."""
    from app.gateway.router import get_engine
    from app.providers.registry import list_providers
    from app.fault_injection.store import is_fault_injection_enabled

    engine = get_engine()
    circuit_snapshots = {s["provider"]: s for s in engine.get_circuit_snapshots()}

    configured = []
    for slug in list_providers():
        key = settings.get_provider_api_key(slug)
        snap = circuit_snapshots.get(slug, {})
        configured.append({
            "provider":       slug,
            "configured":     key is not None,
            "circuit_state":  snap.get("state", "closed"),
            "failure_count":  snap.get("failure_count", 0),
        })

    return {
        "status": "ok",
        "version": "0.4.0",
        "default_provider": settings.default_provider,
        "fault_injection_enabled": is_fault_injection_enabled(),
        "providers": configured,
    }


# ── Routes ─────────────────────────────────────────────────────────────────────
app.include_router(gateway_router)
app.include_router(telemetry_router)
app.include_router(fault_router)
app.include_router(incident_router)


# ── Dev entrypoint ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
