"""
SphinxGate — FastAPI application entry point.

Mounts:
  - CORS middleware (allows the Vite dev server origin)
  - GET  /health             — simple liveness check
  - POST /api/v1/chat/completions — gateway endpoint (Phase 1)
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.gateway.router import router as gateway_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sphinxgate")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SphinxGate",
    description="AI API Gateway — Phase 2 (Resilience Engine)",
    version="0.2.0",
    docs_url="/docs",   # Swagger UI available at http://localhost:8000/docs
    redoc_url="/redoc",
)

settings = get_settings()


# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the Vite dev frontend to call the gateway.
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
    ],
)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health():
    """Simple liveness endpoint. Returns configured providers and their circuit state."""
    from app.gateway.router import get_engine
    from app.providers.registry import list_providers

    engine = get_engine()
    circuit_snapshots = {s["provider"]: s for s in engine.get_circuit_snapshots()}

    configured = []
    for slug in list_providers():
        key = settings.get_provider_api_key(slug)
        snap = circuit_snapshots.get(slug, {})
        configured.append({
            "provider": slug,
            "configured": key is not None,
            "circuit_state": snap.get("state", "closed"),
            "failure_count": snap.get("failure_count", 0),
        })

    return {
        "status": "ok",
        "version": "0.2.0",
        "default_provider": settings.default_provider,
        "providers": configured,
    }


# ── Gateway routes ────────────────────────────────────────────────────────────
app.include_router(gateway_router)


# ── Dev entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
