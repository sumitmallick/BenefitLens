"""Introduce membership_policies + membership_coverage_rules; rename policies.member_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-25

Motivation
----------
A single group/family insurance policy covers multiple members (subscriber +
spouse + dependents).  The previous schema stored only ONE member per policy
via ``policies.member_id``, making group coverage impossible to model.

Additionally, different enrolled members may have different coverage terms:
a child dependent may have 100% pediatric wellness while the base policy is 80%,
or a spouse may carry a different specialist copay.

New design
----------
1. ``policies.holder_member_id``  — replaces ``member_id``.
   Points to the *primary subscriber* (the person who holds the contract).
   Used for billing, premium responsibility, and quick holder look-ups.

2. ``membership_policies`` — junction table (one row per enrolled member).
   The holder is always enrolled with ``relationship = 'SELF'`` on creation.
   Dependents (spouse, children, etc.) are added separately via the API.

3. ``membership_coverage_rules`` — per-member rule overrides (optional).
   Absent service types fall back to the policy-level ``coverage_rules`` default.
   The adjudicator checks member rules first, then policy rules.

Column reference guide
----------------------
membership_policies.relationship      — SELF | SPOUSE | CHILD | OTHER_DEPENDENT
membership_policies.status            — ACTIVE | TERMINATED | SUSPENDED
membership_coverage_rules.*           — same schema as coverage_rules but keyed to
                                        membership_policies.id instead of policies.id

Data migration
--------------
Existing ``policies.member_id`` values are preserved:
  - Copied into ``holder_member_id``.
  - Inserted as a SELF membership row in ``membership_policies``.
  (No member-level coverage rule overrides exist yet; those are added via the API.)

Indexes
-------
  ix_policies_holder_member_id                     — FK look-up for holder
  ix_policies_holder_active (partial, ACTIVE)      — adjudication hot-path
  ix_membership_policies_policy_id                 — enumerate members per policy
  ix_membership_policies_member_id                 — enumerate policies per member
  ix_membership_policies_member_active (partial)   — active coverage check at claim submission
  ix_membership_policies_policy_status             — active roster per policy
  ix_membership_coverage_rules_membership_id       — rule look-up per membership
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Add holder_member_id (nullable during migration) ─────────────
    op.add_column(
        "policies",
        sa.Column(
            "holder_member_id",
            UUID(as_uuid=True),
            sa.ForeignKey("members.id"),
            nullable=True,
            comment="Primary policy holder (subscriber). One policy, many enrolled members.",
        ),
    )

    # ── Step 2: Copy existing member_id into holder_member_id ────────────────
    op.execute("UPDATE policies SET holder_member_id = member_id")

    # ── Step 3: Make holder_member_id NOT NULL now data is populated ─────────
    op.alter_column("policies", "holder_member_id", nullable=False)

    # ── Step 4: Create membership_policies junction table ────────────────────
    op.create_table(
        "membership_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  comment="Surrogate PK — stable enrollment record identifier"),
        sa.Column("policy_id", UUID(as_uuid=True),
                  sa.ForeignKey("policies.id", ondelete="CASCADE"),
                  nullable=False,
                  comment="Policy the member is enrolled under"),
        sa.Column("member_id", UUID(as_uuid=True),
                  sa.ForeignKey("members.id", ondelete="CASCADE"),
                  nullable=False,
                  comment="Enrolled member"),
        sa.Column(
            "relationship",
            sa.String(32),
            nullable=False,
            server_default="SELF",
            comment="Member's relationship to the holder: SELF | SPOUSE | CHILD | OTHER_DEPENDENT",
        ),
        sa.Column("enrollment_date", sa.Date, nullable=False,
                  comment="Date this member's coverage began under the policy"),
        sa.Column("termination_date", sa.Date, nullable=True,
                  comment="Date coverage ended for this member (NULL = still active)"),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="ACTIVE",
            comment="ACTIVE | TERMINATED | SUSPENDED",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # A member may only be enrolled once per policy
        sa.UniqueConstraint("policy_id", "member_id", name="uq_membership_policy_member"),
    )

    # ── Step 5: Create membership_coverage_rules table ───────────────────────
    op.create_table(
        "membership_coverage_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("membership_id", UUID(as_uuid=True),
                  sa.ForeignKey("membership_policies.id", ondelete="CASCADE"),
                  nullable=False,
                  comment="Enrollment record this rule override belongs to"),
        sa.Column("service_type", sa.String(64), nullable=False),
        sa.Column("coverage_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("annual_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("per_visit_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("copay", sa.Numeric(8, 2), nullable=True),
        sa.Column("requires_preauth", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("network_restriction", sa.String(32), nullable=False, server_default="ANY"),
        sa.Column("excluded_diagnosis_codes", JSONB, nullable=False, server_default="[]"),
        sa.UniqueConstraint(
            "membership_id", "service_type",
            name="uq_member_rule_service_type",
        ),
    )

    # ── Step 6: Seed SELF membership for every existing policy ───────────────
    op.execute(
        """
        INSERT INTO membership_policies
            (id, policy_id, member_id, relationship, enrollment_date, status, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            p.id,
            p.member_id,           -- old column, still present at this point
            'SELF',
            p.effective_date,
            p.status,
            NOW(),
            NOW()
        FROM policies p
        """
    )

    # ── Step 7: Drop old indexes that reference member_id column ─────────────
    op.drop_index("ix_policies_member_id", table_name="policies")
    op.drop_index("ix_policies_member_active", table_name="policies")

    # ── Step 8: Drop old member_id column from policies ──────────────────────
    op.drop_column("policies", "member_id")

    # ── Step 9: Indexes on policies.holder_member_id ─────────────────────────
    op.create_index("ix_policies_holder_member_id", "policies", ["holder_member_id"])
    op.create_index(
        "ix_policies_holder_active",
        "policies",
        ["holder_member_id"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # ── Step 10: Indexes on membership_policies ───────────────────────────────
    op.create_index("ix_membership_policies_policy_id", "membership_policies", ["policy_id"])
    op.create_index("ix_membership_policies_member_id", "membership_policies", ["member_id"])
    # Hot path: "is member X covered by any active policy?" — used at claim submission
    op.create_index(
        "ix_membership_policies_member_active",
        "membership_policies",
        ["member_id"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    # Composite: all active members on a policy (admin/UI)
    op.create_index(
        "ix_membership_policies_policy_status",
        "membership_policies",
        ["policy_id", "status"],
    )

    # ── Step 11: Index on membership_coverage_rules ───────────────────────────
    op.create_index(
        "ix_membership_coverage_rules_membership_id",
        "membership_coverage_rules",
        ["membership_id"],
    )


def downgrade() -> None:
    # Drop membership_coverage_rules
    op.drop_index("ix_membership_coverage_rules_membership_id", "membership_coverage_rules")
    op.drop_table("membership_coverage_rules")

    # Drop membership_policies indexes
    op.drop_index("ix_membership_policies_policy_status", "membership_policies")
    op.drop_index("ix_membership_policies_member_active", "membership_policies")
    op.drop_index("ix_membership_policies_member_id", "membership_policies")
    op.drop_index("ix_membership_policies_policy_id", "membership_policies")

    # Drop holder_member_id indexes
    op.drop_index("ix_policies_holder_active", "policies")
    op.drop_index("ix_policies_holder_member_id", "policies")

    # Restore member_id on policies (from holder_member_id)
    op.add_column(
        "policies",
        sa.Column("member_id", UUID(as_uuid=True),
                  sa.ForeignKey("members.id"), nullable=True),
    )
    op.execute("UPDATE policies SET member_id = holder_member_id")
    op.alter_column("policies", "member_id", nullable=False)

    # Drop membership_policies table
    op.drop_table("membership_policies")

    # Remove holder_member_id
    op.drop_column("policies", "holder_member_id")

    # Restore original indexes
    op.create_index("ix_policies_member_id", "policies", ["member_id"])
    op.create_index(
        "ix_policies_member_active",
        "policies",
        ["member_id"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
