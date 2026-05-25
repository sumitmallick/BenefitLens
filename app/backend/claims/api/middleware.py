"""
Request ID middleware + access logging.

Every HTTP request gets a unique X-Request-ID (UUID4).
If the client sends one, it is used as-is (useful for distributed tracing
when the frontend or API gateway stamps the ID before the request arrives).

The ID is:
  - Bound to structlog's context vars so every log line in the request
    carries request_id automatically.
  - Returned in the X-Request-ID response header so clients can correlate
    errors with log entries without needing DB access.

Access log format (structured JSON in prod):
  {"event": "request", "method": "POST", "path": "/api/v1/claims/",
   "status_code": 201, "duration_ms": 42, "request_id": "abc123"}
"""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Assign a unique request ID to every request, log it with timing.

    PHI safety: only path, method, status_code, and duration are logged.
    Request bodies, query params, and headers (other than X-Request-ID)
    are intentionally omitted.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Accept client-provided ID or generate a fresh one
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

        # Bind to structlog context — all downstream log calls inherit this
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response: Response | None = None
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled_exception",
                path=request.url.path,
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            status = response.status_code if response is not None else 500

            # Skip health check noise
            if request.url.path not in ("/health", "/"):
                log = logger.info if status < 400 else logger.warning
                if status >= 500:
                    log = logger.error
                log(
                    "request",
                    status_code=status,
                    duration_ms=duration_ms,
                )

        if response is not None:
            response.headers["X-Request-ID"] = request_id
        return response
