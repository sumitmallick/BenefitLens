"""Add OOP max tracking to policies and HIPAA audit_logs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-18

Changes:
  policies.oop_used  — accumulated out-of-pocket cost-sharing for the benefit year
                       (deductible + copay + coinsurance).  When this reaches
                       out_of_pocket_max the plan covers 100% of subsequent services.

  audit_logs         — HIPAA §164.312(b) audit trail: who accessed which PHI resource,
                       when, from where, and via which request.
                       Retention: retain for minimum 6 years per HIPAA §164.530(j).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── policies.oop_used ─────────────────────────────────────────────────────
    op.add_column(
        "policies",
        sa.Column(
            "oop_used",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
            comment=(
                "Accumulated member cost-sharing (deductible + copay + coinsurance) "
                "for the benefit year.  Compared against out_of_pocket_max during "
                "adjudication to determine if OOP max has been reached."
            ),
        ),
    )

    # ── audit_logs table ──────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # Who
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("user_role", sa.String(50), nullable=True),
        # What
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.UUID(as_uuid=True), nullable=True),
        # Request context
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("http_method", sa.String(10), nullable=True),
        sa.Column("http_path", sa.String(512), nullable=True),
    )

    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index(
        "ix_audit_logs_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_resource", "audit_logs")
    op.drop_index("ix_audit_logs_action", "audit_logs")
    op.drop_index("ix_audit_logs_user_id", "audit_logs")
    op.drop_index("ix_audit_logs_timestamp", "audit_logs")
    op.drop_table("audit_logs")
    op.drop_column("policies", "oop_used")
