"""
FastAPI application entrypoint.

Startup:
  1. Initialize DB connection pool
  2. Initialize PHI encryptor
  3. Register routes
  4. Configure structured logging (JSON in production)
  5. Wire Prometheus metrics + rate limiter

The app is PHI-aware from startup — if encryption is not configured in
a non-dev environment, startup fails rather than silently storing plaintext.
"""
from __future__ import annotations

import asyncio
import sys

import redis.asyncio as aioredis
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from claims.api.deps import get_current_user, require_roles
from claims.api.middleware import RequestIDMiddleware
from claims.api.rate_limit import limiter
from claims.api.routes.auth import router as auth_router
from claims.api.routes.claims import router as claims_router
from claims.api.routes.disputes import router as disputes_router
from claims.api.routes.members import router as members_router
from claims.infrastructure.database import get_session, init_db
from claims.infrastructure.encryption import init_encryptor
from claims.infrastructure.logging import configure_logging, get_logger
from claims.infrastructure.models import UserORM
from config import get_settings

settings = get_settings()

# ── Structured logging ────────────────────────────────────────────────────
configure_logging(environment=settings.environment, log_level=settings.log_level)
logger = get_logger(__name__)

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

# Attach limiter to app state (slowapi reads it from here)
# Rate limiter — Redis-backed, per-IP. Routes opt-in with @limiter.limit("N/minute").
# auth/login: 10/min  auth/register: 5/min  (see claims/api/routes/auth.py)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

# ── Prometheus metrics ────────────────────────────────────────────────────
# Exposes /metrics endpoint scraped by Prometheus every 10 s.
# Grafana reads: http_requests_total, http_request_duration_seconds
Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    excluded_handlers=["/metrics", "/health", "/"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# ── Route registration ────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
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
        "claims_service_started",
        env=settings.environment,
        phi_encryption="active" if settings.phi_encryption_key else "DISABLED_dev_mode",
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # Allow in-flight requests a brief window to complete before the process exits.
    # Kubernetes sends SIGTERM and waits terminationGracePeriodSeconds (default 30s);
    # this sleep buys time for load-balancer health checks to stop routing new traffic.
    logger.info("claims_service_shutdown_initiated")
    await asyncio.sleep(2)
    logger.info("claims_service_shutdown")


# ── Health check (DB + Redis liveness) ───────────────────────────────────

@app.get("/health", tags=["Health"])
async def health(session=Depends(get_session)) -> JSONResponse:
    """
    Liveness + readiness probe.

    Checks:
      - db:    SELECT 1 against PostgreSQL
      - cache: PING to Redis

    Returns HTTP 200 if all checks pass, HTTP 503 if DB is down.
    Redis failure returns 200 with cache=degraded — Redis is not a hard dependency.
    """
    checks: dict[str, str] = {}

    # Database
    try:
        await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        logger.error("health_check_db_failed", error=str(exc))
        checks["db"] = "error"

    # Redis (non-critical — system degrades gracefully without cache)
    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
        checks["cache"] = "ok"
    except Exception:
        checks["cache"] = "degraded"

    db_ok = checks["db"] == "ok"
    overall = "ok" if db_ok and checks["cache"] == "ok" else ("degraded" if db_ok else "error")
    status_code = 200 if db_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "service": "claims-processing", **checks},
    )


@app.get("/", tags=["Health"])
async def root() -> dict:
    return {"service": "claims-processing-api", "docs": "/docs"}


# ── Platform statistics ───────────────────────────────────────────────────

@app.get("/api/v1/stats", tags=["Analytics"])
async def get_platform_stats(
    session=Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
) -> dict:
    """
    Aggregate statistics for the claims platform dashboard.
    Returns counts by entity type and claims breakdown by status.
    No PHI is returned — all values are aggregate counts/rates.
    """
    from datetime import date

    from sqlalchemy import case
    from sqlalchemy import func as sqlfunc
    from sqlalchemy import select

    from claims.infrastructure.models import ClaimORM, MemberORM, PolicyORM

    today = date.today()
    month_start = today.replace(day=1)

    claims_result = await session.execute(
        select(
            sqlfunc.count(ClaimORM.id).label("total"),
            sqlfunc.sum(case((ClaimORM.status == "APPROVED", 1), else_=0)).label("approved"),
            sqlfunc.sum(case((ClaimORM.status == "PARTIALLY_APPROVED", 1), else_=0)).label("partially_approved"),
            sqlfunc.sum(case((ClaimORM.status == "DENIED", 1), else_=0)).label("denied"),
            sqlfunc.sum(case((ClaimORM.status == "SUBMITTED", 1), else_=0)).label("submitted"),
            sqlfunc.sum(case((ClaimORM.status == "UNDER_REVIEW", 1), else_=0)).label("under_review"),
            sqlfunc.sum(case((ClaimORM.status == "DISPUTED", 1), else_=0)).label("disputed"),
            sqlfunc.sum(case((ClaimORM.status == "PAID", 1), else_=0)).label("paid"),
            sqlfunc.sum(case((ClaimORM.submitted_at >= month_start, 1), else_=0)).label("this_month"),
        )
    )
    cr = claims_result.one()

    total = int(cr.total or 0)
    approved = int(cr.approved or 0)
    partially = int(cr.partially_approved or 0)
    denied = int(cr.denied or 0)
    adjudicated = approved + partially + denied
    approval_rate = round((approved + partially) / adjudicated * 100, 1) if adjudicated > 0 else 0.0

    member_count = await session.scalar(select(sqlfunc.count(MemberORM.id))) or 0
    policy_count = await session.scalar(select(sqlfunc.count(PolicyORM.id))) or 0
    active_policy_count = await session.scalar(
        select(sqlfunc.count(PolicyORM.id)).where(PolicyORM.status == "ACTIVE")
    ) or 0

    return {
        "members": {"total": member_count},
        "policies": {"total": policy_count, "active": active_policy_count},
        "claims": {
            "total": total,
            "this_month": int(cr.this_month or 0),
            "by_status": {
                "APPROVED": approved,
                "PARTIALLY_APPROVED": partially,
                "DENIED": denied,
                "SUBMITTED": int(cr.submitted or 0),
                "UNDER_REVIEW": int(cr.under_review or 0),
                "DISPUTED": int(cr.disputed or 0),
                "PAID": int(cr.paid or 0),
            },
        },
        "approval_rate": approval_rate,
    }


# ── Global error handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        exc_type=type(exc).__name__,
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
        timeout_graceful_shutdown=30,
    )
