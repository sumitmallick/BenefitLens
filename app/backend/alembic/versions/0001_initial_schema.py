"""Initial schema: members, policies, coverage_rules, claims, line_items, adjudication_results, disputes, domain_events, annual_usages

Revision ID: 0001
Revises:
Create Date: 2026-05-17

Design notes:
- phi_ prefixed columns hold encrypted ciphertext (AES-128-CBC via Fernet)
- JSONB used for excluded_diagnosis_codes and event payloads (schema-flexible)
- UniqueConstraint on annual_usages prevents duplicate usage rows for same
  (policy, service_type, year) — race condition guard alongside SELECT FOR UPDATE
- All monetary values stored as NUMERIC(12, 2) — exact decimal, no float
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Members
    op.create_table(
        "members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phi_member_id", sa.String(512), nullable=False, unique=True,
                  comment="Encrypted: plan-issued member ID"),
        sa.Column("phi_name", sa.String(512), nullable=False,
                  comment="Encrypted: member full name"),
        sa.Column("phi_date_of_birth", sa.String(512), nullable=False,
                  comment="Encrypted: ISO date of birth"),
        sa.Column("phi_email", sa.String(512), nullable=False,
                  comment="Encrypted: contact email"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Policies
    op.create_table(
        "policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("policy_number", sa.String(64), nullable=False, unique=True),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("expiration_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="ACTIVE"),
        sa.Column("deductible_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("deductible_met", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("out_of_pocket_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_policies_member_id", "policies", ["member_id"])

    # Coverage rules
    op.create_table(
        "coverage_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("service_type", sa.String(64), nullable=False),
        sa.Column("coverage_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("annual_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("per_visit_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("copay", sa.Numeric(8, 2), nullable=True),
        sa.Column("requires_preauth", sa.Boolean, nullable=False, default=False),
        sa.Column("network_restriction", sa.String(32), nullable=False, default="ANY"),
        sa.Column("excluded_diagnosis_codes", JSONB, nullable=False, default=[]),
        sa.UniqueConstraint("policy_id", "service_type", name="uq_policy_service_type"),
    )
    op.create_index("ix_coverage_rules_policy_id", "coverage_rules", ["policy_id"])

    # Annual usages
    op.create_table(
        "annual_usages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("service_type", sa.String(64), nullable=False),
        sa.Column("benefit_year", sa.Integer, nullable=False),
        sa.Column("used_amount", sa.Numeric(12, 2), nullable=False, default=0),
        sa.UniqueConstraint("policy_id", "service_type", "benefit_year", name="uq_usage_policy_service_year"),
    )
    op.create_index("ix_annual_usages_policy_id", "annual_usages", ["policy_id"])

    # Claims
    op.create_table(
        "claims",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_number", sa.String(64), nullable=False, unique=True),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("members.id"), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="SUBMITTED"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_name", sa.String(256), nullable=False),
        sa.Column("provider_npi", sa.String(10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_claims_claim_number", "claims", ["claim_number"])
    op.create_index("ix_claims_member_id", "claims", ["member_id"])

    # Line items
    op.create_table(
        "line_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("service_type", sa.String(64), nullable=False),
        sa.Column("service_date", sa.Date, nullable=False),
        sa.Column("billed_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("phi_diagnosis_code", sa.String(512), nullable=False,
                  comment="Encrypted ICD-10 code"),
        sa.Column("procedure_code", sa.String(16), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="PENDING"),
    )
    op.create_index("ix_line_items_claim_id", "line_items", ["claim_id"])

    # Adjudication results
    op.create_table(
        "adjudication_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("line_item_id", UUID(as_uuid=True), sa.ForeignKey("line_items.id"), nullable=False, unique=True),
        sa.Column("covered_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("denial_reason", sa.String(64), nullable=True),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("adjudicated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deductible_applied", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("copay_applied", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("applied_rule_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_adjudication_results_line_item_id", "adjudication_results", ["line_item_id"])

    # Disputes
    op.create_table(
        "disputes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("line_item_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, default="SUBMITTED"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
    )
    op.create_index("ix_disputes_claim_id", "disputes", ["claim_id"])

    # Domain events (append-only audit log)
    op.create_table(
        "domain_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_domain_events_claim_id", "domain_events", ["claim_id"])


def downgrade() -> None:
    op.drop_table("domain_events")
    op.drop_table("disputes")
    op.drop_table("adjudication_results")
    op.drop_table("line_items")
    op.drop_table("claims")
    op.drop_table("annual_usages")
    op.drop_table("coverage_rules")
    op.drop_table("policies")
    op.drop_table("members")
