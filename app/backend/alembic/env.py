"""
Alembic migration environment.

Runs migrations synchronously (Alembic doesn't support async natively).
The async SQLAlchemy engine is used at runtime; this env uses a sync engine.

Auto-generate usage:
    alembic revision --autogenerate -m "describe your change"

This file imports ALL ORM models so that Alembic's metadata comparison
can detect new/modified/removed tables and columns.

compare_type=True   — detects column type changes (e.g. String(255) → String(512))
compare_server_default=True — detects server_default changes
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
from alembic import context

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import Base and ALL models so Alembic's metadata is fully populated.
# Adding a new ORM model? Import it here so --autogenerate picks it up.
from claims.infrastructure.database import Base          # noqa: E402
from claims.infrastructure import models                 # noqa: F401 — side-effect import
# Explicit model imports ensure nothing is missed even if `models` is split:
from claims.infrastructure.models import (               # noqa: F401
    MemberORM,
    PolicyORM,
    CoverageRuleORM,
    AnnualUsageORM,
    ClaimORM,
    LineItemORM,
    AdjudicationResultORM,
    DisputeORM,
    DomainEventORM,
    UserORM,
    AuditLogORM,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Allow DATABASE_URL_SYNC override from environment (set by Docker Compose)
database_url = os.getenv("DATABASE_URL_SYNC") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection.
    Useful for generating SQL scripts: alembic upgrade head --sql
    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations against a live PostgreSQL connection.
    NullPool prevents connection leaks during one-shot migration runs.

    Advisory lock note: pg_advisory_xact_lock is transaction-scoped and is
    automatically released on commit/rollback — no explicit unlock needed.
    It must be acquired *inside* context.begin_transaction() so it lives in
    the same transaction as the DDL, avoiding the SQLAlchemy 2.x autobegin
    nested-savepoint trap that would silently roll back the schema changes.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            # Transaction-scoped lock — prevents concurrent migration races
            # (e.g. multiple pod startups). Released automatically on commit.
            connection.execute(text("SELECT pg_advisory_xact_lock(1234567890)"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
