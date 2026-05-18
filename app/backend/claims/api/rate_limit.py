"""
Shared rate limiter instance.

Imported by both main.py (to attach to app.state) and individual route
files (to apply @limiter.limit decorators), avoiding circular imports.

Limits are applied per IP address. Redis provides distributed storage so
limits are shared across all pods/replicas.

Auth limits:
  login    — 10/minute  (prevent credential stuffing / brute force)
  register — 5/minute   (prevent account spam)

API limits (applied per-route as needed):
  claims POST — 100/minute per IP
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # opt-in per route; no blanket global limit
)
