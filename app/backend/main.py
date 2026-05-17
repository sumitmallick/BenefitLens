"""
FastAPI application entrypoint.

Startup:
  1. Initialize DB connection pool
  2. Initialize PHI encryptor
  3. Register routes
  4. Configure structured logging (JSON in production)

The app is PHI-aware from startup — if encryption is not configured in
a non-dev environment, startup fails rather than silently storing plaintext.
"""
from __future__ import annotations

import logging
import os
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from claims.api.routes.claims import router as claims_router
from claims.api.routes.disputes import router as disputes_router
from claims.api.routes.members import router as members_router
from claims.infrastructure.database import init_db
from claims.infrastructure.encryption import init_encryptor
from config import get_settings

# ── Logging ───────────────────────────────────────────────────────────────
# Structured logging; in prod, swap handler for JSON formatter + CloudWatch/Datadog.
# PHI fields must NEVER appear in log output. See PHI_SAFE_LOG_FIELDS in config.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

settings = get_settings()

# ── App factory ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Claims Processing System",
    description=(
        "Insurance claims adjudication API. "
        "Handles claim submission, coverage rule evaluation, lifecycle management, "
        "and member dispute resolution."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route registration ────────────────────────────────────────────────────
app.include_router(claims_router, prefix="/api/v1")
app.include_router(disputes_router, prefix="/api/v1")
app.include_router(members_router, prefix="/api/v1")


# ── Startup / Shutdown ────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    init_encryptor(settings.phi_encryption_key)

    if settings.is_production and not settings.phi_encryption_key:
        logger.critical("PHI_ENCRYPTION_KEY not set in production. Aborting.")
        sys.exit(1)

    logger.info(
        "Claims service started — env=%s phi_encryption=%s",
        settings.environment,
        "active" if settings.phi_encryption_key else "DISABLED (dev mode)",
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Claims service shutting down.")


# ── Health check ──────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok", "service": "claims-processing"}


@app.get("/", tags=["Health"])
async def root() -> dict:
    return {"service": "claims-processing-api", "docs": "/docs"}


# ── Global error handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log without PHI — only the URL path and exception type
    logger.error(
        "Unhandled exception: path=%s type=%s",
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
