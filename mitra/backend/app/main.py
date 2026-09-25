"""
MITRA Backend — FastAPI Application Entry Point (Phase 5 — Connectors & Intelligence)

Features:
  - Structured logging via structlog
  - CORS for Tauri WebView origins
  - Prometheus metrics middleware
  - Routers: chat, tools, webhooks, voice, tts, pipeline, connectors, intelligence
  - Health check with circuit breaker and connector status
  - Request latency tracking
"""
from __future__ import annotations

import time
import structlog
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app

from app.config import settings
from app.routers import (
    chat_router,
    tools_router,
    webhooks_router,
    voice_router,
    tts_router,
    pipeline_router,
    connectors_router,
    intelligence_router,
    telemetry_router,
)
from app.models.nim_client import nim_client
from app.connectors.search import search_engine
from app.intelligence.ghost_radar import ghost_radar
from app.intelligence.meeting_guard import meeting_guard

# ---------------------------------------------------------------------------
# Structlog configuration
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.environment == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "mitra_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "mitra_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "mitra.startup",
        app=settings.app_name,
        host=settings.backend_host,
        port=settings.backend_port,
        nim_configured=bool(settings.nim_api_key),
    )
    yield
    # Shutdown
    logger.info("mitra.shutdown")


app = FastAPI(
    title="MITRA Cloud Brain API",
    version="0.5.0",
    description="FastAPI service for Project Sahachara - Phase 5: Connectors, Intelligence, and Automation",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url="/redoc" if settings.environment == "development" else None,
    lifespan=lifespan,
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ---------------------------------------------------------------------------
# CORS — Tauri WebView origins
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "tauri://localhost",
        "http://localhost:1420",
        "http://localhost:5173",
        "http://127.0.0.1:1420",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request timing middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    t_start = time.monotonic()
    response = await call_next(request)
    latency = time.monotonic() - t_start
    endpoint = request.url.path
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(latency)
    response.headers["X-Process-Time-Ms"] = f"{latency * 1000:.2f}"
    return response

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(chat_router)
app.include_router(tools_router)
app.include_router(webhooks_router)
# Phase 4: Voice Pipeline routers
app.include_router(voice_router)
app.include_router(tts_router)
app.include_router(pipeline_router)
# Phase 5: Connectors & Intelligence routers
app.include_router(connectors_router)
app.include_router(intelligence_router)
# Phase 7: Telemetry & Privacy compliance routers
app.include_router(telemetry_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Extended health check:
      - App status
      - NIM API key configured
      - Circuit breaker status per role
      - Voice pipeline config
      - Phase 5 Connectors & Intelligence status
    """
    breaker_status = nim_client.get_breaker_status()
    any_tripped = any(v["is_open"] for v in breaker_status.values())

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "0.5.0",
        "environment": settings.environment,
        "nim_configured": bool(settings.nim_api_key),
        "circuit_breakers": breaker_status,
        "any_circuit_tripped": any_tripped,
        "voice_pipeline": {
            "stt_model": settings.model_stt,
            "tts_primary": "kokoro-82M",
            "tts_fallback": "cartesia/sonic-english",
            "kokoro_url": settings.kokoro_base_url,
            "aec_enabled": settings.aec_mute_on_tts,
        },
        "phase5_intelligence": {
            "connectors": ["google_workspace", "microsoft_365", "n8n_automation"],
            "search_chunks_indexed": len(search_engine._corpus),
            "commitments_tracked": len(ghost_radar._commitments),
            "meeting_guard_active": meeting_guard._is_meeting_active,
            "undo_buffer_seconds": 10.0,
        },
    }


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level="debug",
    )
