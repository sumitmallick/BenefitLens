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

import sys

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from claims.api.deps import get_current_user, require_roles
from claims.api.middleware import RequestIDMiddleware
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
# JSON in production (consumed by Promtail → Loki → Grafana).
# ConsoleRenderer with colours in development.
# PHI fields (phi_* prefix) are stripped by the logging pipeline before render.
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
# Provides: http_requests_total, http_request_duration_seconds (histogram)
# Grafana dashboard reads these via the Prometheus data source.
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
    logger.info("claims_service_shutdown")


# ── Health check ──────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok", "service": "claims-processing"}


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
    from sqlalchemy import func as sqlfunc, select, case
    from claims.infrastructure.models import ClaimORM, MemberORM, PolicyORM
    from datetime import date, timedelta

    today = date.today()
    month_start = today.replace(day=1)

    # Claims stats with status breakdown
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

    # Member and policy counts
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
    # Log without PHI — only the URL path and exception type
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
    )
