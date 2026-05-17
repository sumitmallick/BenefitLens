"""
Structured logging configuration for ClaimsIQ.

Uses structlog with two renderers:
  - Development: pretty ConsoleRenderer (human-readable, coloured)
  - Production:  JSONRenderer (one JSON object per line — Loki-parseable)

PHI safety:
  - The phi_filter processor strips any key whose name starts with "phi_"
    before the log event is rendered. This prevents accidental PHI leakage
    through log calls even if a developer forgets to redact manually.

Request tracing:
  - RequestIDMiddleware (in claims/api/middleware.py) generates/accepts
    X-Request-ID and binds it to structlog's context var so every log
    line in a request carries request_id automatically.

Usage:
    from claims.infrastructure.logging import get_logger
    log = get_logger(__name__)
    log.info("claim_submitted", claim_number="CLM-001", member_id=str(member_id))
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# ── PHI filter ────────────────────────────────────────────────────────────

def _phi_filter(
    logger: Any,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: dict,
) -> dict:
    """
    Strip any key prefixed with 'phi_' from the log event dict.
    Runs before rendering so PHI never reaches the log sink.
    """
    keys_to_drop = [k for k in event_dict if k.startswith("phi_")]
    for k in keys_to_drop:
        del event_dict[k]
    return event_dict


# ── Shared processors ─────────────────────────────────────────────────────

SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,        # inject request_id etc.
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    _phi_filter,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def configure_logging(environment: str = "development", log_level: str = "INFO") -> None:
    """
    Call once at application startup (main.py on_startup).

    In development: coloured, human-readable output.
    In production:  JSON output consumed by Promtail → Loki → Grafana.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    if environment == "production":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=SHARED_PROCESSORS + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge structlog into stdlib logging so third-party libs (uvicorn, sqlalchemy)
    # go through the same pipeline.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)
