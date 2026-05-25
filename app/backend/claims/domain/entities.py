"""
Core domain entities for the Claims Processing System.

Design principles:
  - Entities own their invariants (constructor validation).
  - Entities do NOT talk to the database.
  - PHI fields (name, dob, diagnosis codes) are annotated; the
    infrastructure layer encrypts them before persistence.
  - UUIDs as primary identifiers — avoids sequential ID enumeration.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from .value_objects import (
    ClaimStatus,
    DenialReason,
    DiagnosisCode,
    DisputeStatus,
    LineItemStatus,
    Money,
    NetworkType,
    PolicyStatus,
    ProcedureCode,
    ServiceType,
)


# ---------------------------------------------------------------------------
# Coverage rule (embedded in Policy)
# ---------------------------------------------------------------------------

@dataclass
class CoverageRule:
    """
    Encodes what the policy pays for a given service type.

    annual_limit=None means no cap.
    per_visit_limit=None means no per-visit cap.
    copay=None means no copay (coverage_percentage applies to full amount).
    excluded_diagnosis_codes: if a line item's diagnosis matches, the rule
        yields EXCLUDED_DIAGNOSIS denial even if service type matches.
    """
    id: uuid.UUID
    policy_id: uuid.UUID
    service_type: ServiceType
    coverage_percentage: Decimal           # 0.0 – 100.0
    annual_limit: Optional[Money]
    per_visit_limit: Optional[Money]
    copay: Optional[Money]
    requires_preauth: bool
    network_restriction: NetworkType
    excluded_diagnosis_codes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.coverage_percentage <= Decimal("100")):
            raise ValueError(
                f"coverage_percentage must be 0–100, got {self.coverage_percentage}"
            )

    @property
    def coverage_factor(self) -> Decimal:
        return self.coverage_percentage / Decimal("100")


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

@dataclass
class MembershipPolicy:
    """
    A member's enrollment record under a specific policy.

    A policy can cover multiple members: the primary subscriber (SELF) plus
    any dependents (SPOUSE, CHILD, OTHER_DEPENDENT) added later.

    enrollment_date: when this member's coverage began under the policy.
    termination_date: None means coverage is still active.
    status: ACTIVE | TERMINATED | SUSPENDED
    """
    id: uuid.UUID
    policy_id: uuid.UUID
    member_id: uuid.UUID
    relationship: str           # SELF | SPOUSE | CHILD | OTHER_DEPENDENT
    enrollment_date: date
    termination_date: Optional[date]
    status: str
    created_at: datetime
    updated_at: datetime

    # Per-member coverage rule overrides.
    # Empty list means: use the policy's default coverage rules for all service types.
    # When non-empty, each rule here overrides the matching policy rule for this member only.
    coverage_rules: List["CoverageRule"] = field(default_factory=list)

    def is_active_on(self, service_date: date) -> bool:
        """Return True if this membership is active and covers the given date."""
        if self.status != "ACTIVE":
            return False
        if service_date < self.enrollment_date:
            return False
        if self.termination_date and service_date > self.termination_date:
            return False
        return True

    def rule_for(self, service_type) -> "Optional[CoverageRule]":
        """
        Return the member-specific override rule for a service type, or None if
        this member uses the policy default for that service type.
        """
        return next((r for r in self.coverage_rules if r.service_type == service_type), None)


@dataclass
class Policy:
    """
    The contract between the insurer and the primary subscriber.

    holder_member_id: the primary subscriber who holds the contract and is
        responsible for premiums.  Multiple members can be enrolled under this
        policy via the membership_policies table.

    deductible_amount: the annual deductible the member must meet before
        the insurer starts paying (applies to non-preventive services).
    deductible_met: accumulated amount credited toward the deductible this year.
    """
    id: uuid.UUID
    holder_member_id: uuid.UUID
    policy_number: str
    effective_date: date
    expiration_date: date
    status: PolicyStatus
    deductible_amount: Money
    deductible_met: Money
    out_of_pocket_max: Optional[Money]
    coverage_rules: List[CoverageRule] = field(default_factory=list)
    # Tracks accumulated out-of-pocket costs (deductible + copay + coinsurance)
    # for this benefit year. Mutated by the adjudicator alongside deductible_met.
    oop_used: Money = field(default_factory=Money.zero)

    def is_active_on(self, service_date: date) -> bool:
        return (
            self.status == PolicyStatus.ACTIVE
            and self.effective_date <= service_date <= self.expiration_date
        )

    def rule_for(self, service_type: ServiceType) -> Optional[CoverageRule]:
        """Return the first matching coverage rule, or None if not covered."""
        return next(
            (r for r in self.coverage_rules if r.service_type == service_type),
            None,
        )

    @property
    def remaining_deductible(self) -> Money:
        return self.deductible_amount - self.deductible_met

    def apply_deductible(self, amount: Money) -> tuple[Money, Money]:
        """
        Given a billed amount, return (amount_applied_to_deductible, remainder).
        Mutates deductible_met.
        """
        remaining = self.remaining_deductible
        applied = Money(min(remaining.amount, amount.amount))
        self.deductible_met = self.deductible_met + applied
        remainder = amount - applied
        return applied, remainder

    @property
    def oop_remaining(self) -> Optional[Money]:
        """None means no OOP max applies (unlimited)."""
        if self.out_of_pocket_max is None:
            return None
        return self.out_of_pocket_max - self.oop_used

    def apply_oop_max(self, member_cost_sharing: Money) -> tuple[Money, Money]:
        """
        Given member cost-sharing (deductible + copay + coinsurance) for a line item,
        return (actual_member_cost, insurer_subsidy).

        If applying member_cost_sharing would exceed the OOP max, the insurer
        picks up the difference (subsidy > 0). Mutates oop_used.

        Returns:
          actual_member_cost  — what the member actually pays after OOP cap
          insurer_subsidy     — additional covered amount from OOP protection
        """
        if self.out_of_pocket_max is None:
            self.oop_used = self.oop_used + member_cost_sharing
            return member_cost_sharing, Money.zero()

        remaining = self.oop_remaining
        if member_cost_sharing <= remaining:
            self.oop_used = self.oop_used + member_cost_sharing
            return member_cost_sharing, Money.zero()

        # OOP max kicked in — insurer covers the excess
        insurer_subsidy = member_cost_sharing - remaining
        self.oop_used = self.out_of_pocket_max  # now fully met
        return remaining, insurer_subsidy


# ---------------------------------------------------------------------------
# Annual usage tracking
# ---------------------------------------------------------------------------

@dataclass
class AnnualUsage:
    """
    Tracks dollars consumed under a specific coverage rule in a benefit year.
    One row per (policy_id, service_type, benefit_year).
    """
    id: uuid.UUID
    policy_id: uuid.UUID
    service_type: ServiceType
    benefit_year: int
    used_amount: Money

    def remaining(self, limit: Optional[Money]) -> Optional[Money]:
        if limit is None:
            return None  # no cap
        return limit - self.used_amount

    def consume(self, amount: Money) -> None:
        self.used_amount = self.used_amount + amount


# ---------------------------------------------------------------------------
# Member  (PHI fields annotated for encryption in the infra layer)
# ---------------------------------------------------------------------------

@dataclass
class Member:
    """
    PHI fields: name, date_of_birth.
    The infrastructure layer stores these AES-256 encrypted.
    member_id is a plan-issued identifier (e.g., "MBR-00123").
    """
    id: uuid.UUID
    member_id: str            # PHI: plan-issued member ID
    name: str                 # PHI
    date_of_birth: date       # PHI
    email: str                # PHI (contact, not health data)
    policies: List[Policy] = field(default_factory=list)

    def active_policy_on(self, service_date: date) -> Optional[Policy]:
        return next((p for p in self.policies if p.is_active_on(service_date)), None)


# ---------------------------------------------------------------------------
# Adjudication result
# ---------------------------------------------------------------------------

@dataclass
class AdjudicationResult:
    """
    The output of running the adjudicator against a single line item.

    explanation is human-readable prose surfaced directly to the member.
    denial_reason is a structured code for downstream reporting.
    """
    id: uuid.UUID
    line_item_id: uuid.UUID
    covered_amount: Money
    denial_reason: Optional[DenialReason]
    explanation: str
    adjudicated_at: datetime
    deductible_applied: Money
    copay_applied: Money
    applied_rule_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Line item
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    """
    A single service/procedure within a claim.

    diagnosis_code is PHI (ICD-10); stored encrypted.
    billed_amount is what the provider charged; covered_amount is what
    the insurer will pay (set after adjudication).
    """
    id: uuid.UUID
    claim_id: uuid.UUID
    service_type: ServiceType
    service_date: date
    billed_amount: Money
    diagnosis_code: str          # PHI — ICD-10 format, stored encrypted
    procedure_code: str
    description: str
    status: LineItemStatus = LineItemStatus.PENDING
    adjudication: Optional[AdjudicationResult] = None

    def __post_init__(self) -> None:
        # Validate codes on construction — catch bad data at the boundary
        DiagnosisCode(self.diagnosis_code)
        ProcedureCode(self.procedure_code)
        if self.billed_amount.is_zero:
            raise ValueError("LineItem billed_amount must be > 0")


# ---------------------------------------------------------------------------
# Domain events (lightweight — carried on Claim, published async)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    occurred_at: datetime
    aggregate_id: uuid.UUID
    payload: dict


# ---------------------------------------------------------------------------
# Claim (aggregate root)
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """
    The aggregate root for the claims domain.

    Claim owns LineItems and accumulates DomainEvents.
    Events are published by the application service after the transaction
    commits — the domain itself stays free of I/O.

    claim_number follows pattern CLM-YYYYMMDD-<6-char-random>.
    """
    id: uuid.UUID
    claim_number: str
    member_id: uuid.UUID
    policy_id: uuid.UUID
    status: ClaimStatus
    submitted_at: datetime
    provider_name: str
    provider_npi: str              # National Provider Identifier
    line_items: List[LineItem] = field(default_factory=list)
    events: List[DomainEvent] = field(default_factory=list)
    updated_at: Optional[datetime] = None

    # ------------------------------------------------------------------ #
    # Domain behaviour                                                     #
    # ------------------------------------------------------------------ #

    def add_line_item(self, line_item: LineItem) -> None:
        if self.status != ClaimStatus.SUBMITTED:
            raise ValueError(
                f"Cannot add line items to a claim in status {self.status!r}"
            )
        if line_item.claim_id != self.id:
            raise ValueError("LineItem does not belong to this Claim")
        self.line_items.append(line_item)

    def record_event(self, event_type: str, payload: dict) -> None:
        self.events.append(
            DomainEvent(
                event_type=event_type,
                occurred_at=datetime.utcnow(),
                aggregate_id=self.id,
                payload=payload,
            )
        )

    def all_line_items_adjudicated(self) -> bool:
        return all(
            li.status != LineItemStatus.PENDING for li in self.line_items
        )

    @property
    def total_billed(self) -> Money:
        total = Money.zero()
        for li in self.line_items:
            total = total + li.billed_amount
        return total

    @property
    def total_covered(self) -> Money:
        total = Money.zero()
        for li in self.line_items:
            if li.adjudication:
                total = total + li.adjudication.covered_amount
        return total


# ---------------------------------------------------------------------------
# Dispute
# ---------------------------------------------------------------------------

@dataclass
class Dispute:
    """
    A member's challenge to a specific claim (or individual line item) decision.

    line_item_id=None means the member is disputing the entire claim outcome.
    """
    id: uuid.UUID
    claim_id: uuid.UUID
    line_item_id: Optional[uuid.UUID]
    reason: str
    status: DisputeStatus
    submitted_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None

    def resolve(self, outcome: DisputeStatus, notes: str) -> None:
        if outcome not in (DisputeStatus.UPHELD, DisputeStatus.DENIED):
            raise ValueError(f"Invalid dispute resolution outcome: {outcome!r}")
        self.status = outcome
        self.resolved_at = datetime.utcnow()
        self.resolution_notes = notes
