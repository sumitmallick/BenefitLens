"""Add composite indexes for query performance at scale

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-17

Scale design rationale:
  - claims(member_id, status)        → patient dashboard (own claims by status)
  - claims(provider_npi, submitted_at)→ provider dashboard (own submissions over time)
  - claims(status, submitted_at)     → claims queue sorted newest first by status
  - disputes(claim_id, status)       → dispute lookup per claim
  - policies(member_id, status)      → active policy check (hot path in adjudication)
  - line_items(claim_id, status)     → line item status rollup per claim
  - users(role, is_active)           → admin user management filter

  Partial index on policies where status='ACTIVE' eliminates inactive policy rows
  from adjudication lookups — significant at scale (most policies are eventually inactive).

  Table partitioning (for claims > 10M rows):
    Recommend PARTITION BY RANGE (submitted_at) with monthly partitions.
    Not applied here to keep the migration reversible without data movement.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Claims composite indexes ──────────────────────────────────────────────
    # Patient dashboard: list own claims filtered by status
    op.create_index(
        "ix_claims_member_status",
        "claims",
        ["member_id", "status"],
    )
    # Provider dashboard: list own submissions newest-first
    op.create_index(
        "ix_claims_provider_submitted",
        "claims",
        ["provider_npi", "submitted_at"],
    )
    # Claims queue: status filter + time ordering (most common admin query)
    op.create_index(
        "ix_claims_status_submitted",
        "claims",
        ["status", "submitted_at"],
    )

    # ── Disputes ──────────────────────────────────────────────────────────────
    op.create_index(
        "ix_disputes_claim_status",
        "disputes",
        ["claim_id", "status"],
    )

    # ── Policies partial index ────────────────────────────────────────────────
    # Adjudication hot path: active policy lookup is O(active policies for member)
    # not O(all policies for member)
    op.create_index(
        "ix_policies_member_active",
        "policies",
        ["member_id"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # ── Line items ────────────────────────────────────────────────────────────
    op.create_index(
        "ix_line_items_claim_status",
        "line_items",
        ["claim_id", "status"],
    )

    # ── Users ─────────────────────────────────────────────────────────────────
    op.create_index(
        "ix_users_role_active",
        "users",
        ["role", "is_active"],
    )

    # ── Domain events: range scan on event_type per claim ─────────────────────
    op.create_index(
        "ix_domain_events_claim_type",
        "domain_events",
        ["claim_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_domain_events_claim_type", "domain_events")
    op.drop_index("ix_users_role_active", "users")
    op.drop_index("ix_line_items_claim_status", "line_items")
    op.drop_index("ix_policies_member_active", "policies")
    op.drop_index("ix_disputes_claim_status", "disputes")
    op.drop_index("ix_claims_status_submitted", "claims")
    op.drop_index("ix_claims_provider_submitted", "claims")
    op.drop_index("ix_claims_member_status", "claims")
