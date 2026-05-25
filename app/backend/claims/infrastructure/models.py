"""
SQLAlchemy ORM models (persistence layer).

These are intentionally separate from domain entities.
The mapper layer (repositories) translates between ORM rows and domain objects.

PHI columns are prefixed with phi_ to make them obvious in schema migrations.
At the database level they hold encrypted ciphertext.

Pessimistic locking for annual_usage is implemented with SELECT FOR UPDATE
in the repository (not here) to prevent double-spend on annual limits
under concurrent requests.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class MemberORM(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phi_member_id: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, comment="Encrypted: plan-issued member ID")
    phi_name: Mapped[str] = mapped_column(String(512), nullable=False, comment="Encrypted: member full name")
    phi_date_of_birth: Mapped[str] = mapped_column(String(512), nullable=False, comment="Encrypted: ISO date")
    phi_email: Mapped[str] = mapped_column(String(512), nullable=False, comment="Encrypted: contact email")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Policies where this member is the primary subscriber (contract holder)
    held_policies: Mapped[List["PolicyORM"]] = relationship(
        "PolicyORM", back_populates="holder_member", lazy="select",
        foreign_keys="PolicyORM.holder_member_id",
    )
    # All policies this member is enrolled in (as holder OR dependent)
    memberships: Mapped[List["MembershipPolicyORM"]] = relationship(
        "MembershipPolicyORM", back_populates="member", lazy="selectin",
    )
    claims: Mapped[List["ClaimORM"]] = relationship("ClaimORM", back_populates="member", lazy="selectin")


class PolicyORM(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Primary subscriber — the person who holds the contract and owns the benefit year accumulators.
    # Multiple members may be enrolled under this policy via membership_policies.
    holder_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id"), nullable=False, index=True,
        comment="Primary subscriber (contract holder)",
    )
    policy_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    deductible_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deductible_met: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    out_of_pocket_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    # Accumulated member cost-sharing (deductible + copay + coinsurance) this benefit year.
    # When oop_used reaches out_of_pocket_max, the insurer covers 100% of subsequent covered services.
    oop_used: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    holder_member: Mapped["MemberORM"] = relationship(
        "MemberORM", back_populates="held_policies", foreign_keys=[holder_member_id],
    )
    # All enrollment records for this policy (one per covered member)
    memberships: Mapped[List["MembershipPolicyORM"]] = relationship(
        "MembershipPolicyORM", back_populates="policy", lazy="select",
    )
    coverage_rules: Mapped[List["CoverageRuleORM"]] = relationship(
        "CoverageRuleORM", back_populates="policy", lazy="selectin"
    )
    annual_usages: Mapped[List["AnnualUsageORM"]] = relationship("AnnualUsageORM", back_populates="policy")
    claims: Mapped[List["ClaimORM"]] = relationship("ClaimORM", back_populates="policy")


class MembershipPolicyORM(Base):
    """
    Junction table: one row per (member, policy) enrollment.

    The primary subscriber is always present with relationship='SELF'.
    Dependents are added via the membership management API.

    termination_date=None means coverage is still active for this member.
    status mirrors the administrative state; use is_active_on() for date-aware checks.
    """
    __tablename__ = "membership_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    relationship: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SELF",
        comment="SELF | SPOUSE | CHILD | OTHER_DEPENDENT",
    )
    enrollment_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("policy_id", "member_id", name="uq_membership_policy_member"),
    )

    policy: Mapped["PolicyORM"] = relationship("PolicyORM", back_populates="memberships")
    member: Mapped["MemberORM"] = relationship("MemberORM", back_populates="memberships")


class CoverageRuleORM(Base):
    __tablename__ = "coverage_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(64), nullable=False)
    coverage_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    annual_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    per_visit_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    copay: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    requires_preauth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    network_restriction: Mapped[str] = mapped_column(String(32), nullable=False, default="ANY")
    excluded_diagnosis_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("policy_id", "service_type", name="uq_policy_service_type"),
    )

    policy: Mapped["PolicyORM"] = relationship("PolicyORM", back_populates="coverage_rules")


class AnnualUsageORM(Base):
    __tablename__ = "annual_usages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(64), nullable=False)
    benefit_year: Mapped[int] = mapped_column(Integer, nullable=False)
    used_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    __table_args__ = (
        UniqueConstraint("policy_id", "service_type", "benefit_year", name="uq_usage_policy_service_year"),
    )

    policy: Mapped["PolicyORM"] = relationship("PolicyORM", back_populates="annual_usages")


class ClaimORM(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policies.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUBMITTED")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_npi: Mapped[str] = mapped_column(String(10), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    member: Mapped["MemberORM"] = relationship("MemberORM", back_populates="claims")
    policy: Mapped["PolicyORM"] = relationship("PolicyORM", back_populates="claims")
    line_items: Mapped[List["LineItemORM"]] = relationship(
        "LineItemORM", back_populates="claim", lazy="selectin"
    )
    disputes: Mapped[List["DisputeORM"]] = relationship("DisputeORM", back_populates="claim")
    domain_events: Mapped[List["DomainEventORM"]] = relationship("DomainEventORM", back_populates="claim")


class LineItemORM(Base):
    __tablename__ = "line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(64), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    phi_diagnosis_code: Mapped[str] = mapped_column(String(512), nullable=False, comment="Encrypted ICD-10 code")
    procedure_code: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")

    claim: Mapped["ClaimORM"] = relationship("ClaimORM", back_populates="line_items")
    adjudication: Mapped[Optional["AdjudicationResultORM"]] = relationship(
        "AdjudicationResultORM", back_populates="line_item", uselist=False, lazy="selectin"
    )


class AdjudicationResultORM(Base):
    __tablename__ = "adjudication_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("line_items.id"), nullable=False, unique=True, index=True
    )
    covered_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    denial_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    adjudicated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deductible_applied: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    copay_applied: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    applied_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    line_item: Mapped["LineItemORM"] = relationship("LineItemORM", back_populates="adjudication")


class DisputeORM(Base):
    __tablename__ = "disputes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    line_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUBMITTED")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    claim: Mapped["ClaimORM"] = relationship("ClaimORM", back_populates="disputes")


class DomainEventORM(Base):
    __tablename__ = "domain_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    claim: Mapped["ClaimORM"] = relationship("ClaimORM", back_populates="domain_events")


class UserORM(Base):
    """
    Platform user accounts with RBAC roles.

    Roles:
      ADMIN          — full access to all resources and user management
      CLAIM_PROCESSOR — claims queue, adjudication, dispute resolution
      PATIENT        — own claims/profile only (linked via member_id)
      PROVIDER       — submit claims + view own submissions (linked via provider_npi)
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="PATIENT")

    # PATIENT link — may be null until admin links the account to a member record
    member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )

    # PROVIDER identity — must match provider_npi used in claim submissions
    provider_npi: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    provider_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLogORM(Base):
    """
    HIPAA-compliant audit trail: who accessed which PHI resource, when, and from where.

    Every read of a claim detail, member record, or dispute that could expose PHI
    must insert a row here. The application service layer handles insertion via
    AuditLogRepository so routes stay clean.

    Retention: retain audit logs for minimum 6 years (HIPAA §164.530(j)).
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Who performed the action
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # What action was performed
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # e.g. VIEW_CLAIM_DETAIL, SUBMIT_CLAIM, PAY_CLAIM, VIEW_MEMBER,
    #      SUBMIT_DISPUTE, RESOLVE_DISPUTE, EXPORT_CLAIMS

    # Which resource was accessed
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g. claim, member, policy, dispute
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Request context (for forensics)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)   # IPv6 max = 45 chars
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)   # X-Request-ID correlation
    http_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    http_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
