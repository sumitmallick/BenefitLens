"""
Application service — orchestrates domain objects and infrastructure.

This layer:
  - Assembles domain objects from the DB (via repositories)
  - Calls the adjudicator (pure domain function)
  - Persists results
  - Publishes domain events (fire-and-forget post-commit)

NOT responsible for:
  - HTTP concerns (those live in the API layer)
  - Business rules (those live in the domain layer)
"""
from __future__ import annotations

import logging
import random
import string
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from claims.domain.adjudicator import AdjudicationContext, adjudicate
from claims.domain.entities import (
    AnnualUsage,
    Claim,
    CoverageRule,
    Dispute,
    LineItem,
    Member,
    Policy,
)
from claims.domain.events import ClaimStatusChanged, ClaimSubmitted, LineItemAdjudicated
from claims.domain.state_machines import (
    derive_claim_status_from_line_items,
    transition_claim,
    transition_dispute,
)
from claims.domain.value_objects import (
    ClaimStatus,
    DenialReason,
    DisputeStatus,
    LineItemStatus,
    Money,
    NetworkType,
    PolicyStatus,
    ServiceType,
)
from claims.infrastructure.repositories import (
    AnnualUsageRepository,
    ClaimRepository,
    DisputeRepository,
    MemberRepository,
    PolicyRepository,
)

logger = logging.getLogger(__name__)


class ClaimNotFound(Exception):
    pass


class PolicyNotFound(Exception):
    pass


class MemberNotFound(Exception):
    pass


class InvalidClaimState(Exception):
    pass


class DisputeNotFound(Exception):
    pass


# ── Claim number generation ───────────────────────────────────────────────

def _generate_claim_number() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"CLM-{datetime.utcnow().strftime('%Y%m%d')}-{suffix}"


# ── Submit claim ──────────────────────────────────────────────────────────

class SubmitClaimCommand:
    def __init__(
        self,
        member_id: uuid.UUID,
        policy_id: uuid.UUID,
        provider_name: str,
        provider_npi: str,
        line_items: List[dict],  # raw dicts from API
    ) -> None:
        self.member_id = member_id
        self.policy_id = policy_id
        self.provider_name = provider_name
        self.provider_npi = provider_npi
        self.line_items = line_items


async def submit_claim(cmd: SubmitClaimCommand, session: AsyncSession) -> Claim:
    """
    Submit a new claim.

    Validates policy existence and membership. Does NOT adjudicate yet —
    adjudication runs as a separate step so it can be async/queued.
    For this implementation, adjudication is triggered immediately after
    submission (synchronous for simplicity; see decisions.md).
    """
    member_repo = MemberRepository(session)
    policy_repo = PolicyRepository(session)
    claim_repo = ClaimRepository(session)

    # Validate member
    member = await member_repo.get(cmd.member_id)
    if not member:
        raise MemberNotFound(f"Member {cmd.member_id} not found")

    # Validate policy belongs to member
    policy = await policy_repo.get(cmd.policy_id)
    if not policy or policy.member_id != cmd.member_id:
        raise PolicyNotFound(
            f"Policy {cmd.policy_id} not found for member {cmd.member_id}"
        )

    claim_id = uuid.uuid4()
    now = datetime.utcnow()

    line_items = []
    for raw in cmd.line_items:
        li = LineItem(
            id=uuid.uuid4(),
            claim_id=claim_id,
            service_type=ServiceType(raw["service_type"]),
            service_date=date.fromisoformat(raw["service_date"]) if isinstance(raw["service_date"], str) else raw["service_date"],
            billed_amount=Money.of(str(raw["billed_amount"])),
            diagnosis_code=raw["diagnosis_code"],
            procedure_code=raw["procedure_code"],
            description=raw.get("description", ""),
        )
        line_items.append(li)

    claim = Claim(
        id=claim_id,
        claim_number=_generate_claim_number(),
        member_id=cmd.member_id,
        policy_id=cmd.policy_id,
        status=ClaimStatus.SUBMITTED,
        submitted_at=now,
        provider_name=cmd.provider_name,
        provider_npi=cmd.provider_npi,
        line_items=line_items,
    )

    claim.record_event("ClaimSubmitted", {
        "claim_number": claim.claim_number,
        "member_id": str(claim.member_id),
        "line_item_count": len(line_items),
        "total_billed_cents": int(claim.total_billed.amount * 100),
    })

    await claim_repo.save(claim)
    logger.info("Claim submitted: %s", claim.claim_number)

    # Trigger adjudication immediately (synchronous for now)
    return await adjudicate_claim(claim.id, session)


# ── Adjudicate claim ──────────────────────────────────────────────────────

async def adjudicate_claim(claim_id: uuid.UUID, session: AsyncSession) -> Claim:
    """
    Run the adjudicator over all pending line items.

    Uses SELECT FOR UPDATE on AnnualUsage rows to prevent concurrent
    double-spend on annual limits. Each line item is processed in order;
    the annual limit is updated atomically per line item.
    """
    claim_repo = ClaimRepository(session)
    policy_repo = PolicyRepository(session)
    usage_repo = AnnualUsageRepository(session)

    claim = await claim_repo.get(claim_id)
    if not claim:
        raise ClaimNotFound(f"Claim {claim_id} not found")

    policy = await policy_repo.get(claim.policy_id)
    if not policy:
        raise PolicyNotFound(f"Policy {claim.policy_id} not found")

    # Transition claim to UNDER_REVIEW
    prev_status = claim.status
    claim.status = transition_claim(claim.status, ClaimStatus.UNDER_REVIEW)
    await claim_repo.save(claim)

    # Adjudicate each pending line item
    for li in claim.line_items:
        if li.status != LineItemStatus.PENDING:
            continue

        # Lock annual usage row for this service type + year
        usage_orm = await usage_repo.get_for_update(
            policy_id=policy.id,
            service_type=li.service_type,
            benefit_year=li.service_date.year,
        )

        # Map ORM → domain or create new
        if usage_orm:
            usage = AnnualUsage(
                id=usage_orm.id,
                policy_id=usage_orm.policy_id,
                service_type=ServiceType(usage_orm.service_type),
                benefit_year=usage_orm.benefit_year,
                used_amount=Money(usage_orm.used_amount),
            )
        else:
            usage = None

        ctx = AdjudicationContext(policy=policy, annual_usage=usage)
        li, updated_usage = adjudicate(li, ctx)

        if updated_usage:
            await usage_repo.save(updated_usage)

        claim.record_event("LineItemAdjudicated", {
            "line_item_id": str(li.id),
            "service_type": li.service_type.value,
            "status": li.status.value,
            "covered_amount_cents": int(li.adjudication.covered_amount.amount * 100) if li.adjudication else 0,
            "denial_reason": li.adjudication.denial_reason.value if li.adjudication and li.adjudication.denial_reason else None,
        })

    # Derive claim status from line item outcomes
    line_item_statuses = [li.status for li in claim.line_items]
    new_claim_status = derive_claim_status_from_line_items(line_item_statuses)

    # Only apply valid state transition
    if new_claim_status != ClaimStatus.UNDER_REVIEW:
        claim.status = transition_claim(ClaimStatus.UNDER_REVIEW, new_claim_status)
    else:
        claim.status = ClaimStatus.UNDER_REVIEW

    claim.record_event("ClaimStatusChanged", {
        "from": prev_status.value,
        "to": claim.status.value,
    })

    await claim_repo.save(claim)
    logger.info("Claim adjudicated: %s → %s", claim.claim_number, claim.status.value)
    return claim


# ── Get claim ─────────────────────────────────────────────────────────────

async def get_claim(claim_id: uuid.UUID, session: AsyncSession) -> Claim:
    repo = ClaimRepository(session)
    claim = await repo.get(claim_id)
    if not claim:
        raise ClaimNotFound(f"Claim {claim_id} not found")
    return claim


async def list_claims_for_member(member_id: uuid.UUID, session: AsyncSession) -> List[Claim]:
    repo = ClaimRepository(session)
    return await repo.list_by_member(member_id)


# ── Mark claim paid ───────────────────────────────────────────────────────

async def mark_claim_paid(claim_id: uuid.UUID, session: AsyncSession) -> Claim:
    repo = ClaimRepository(session)
    claim = await repo.get(claim_id)
    if not claim:
        raise ClaimNotFound(f"Claim {claim_id} not found")

    claim.status = transition_claim(claim.status, ClaimStatus.PAID)
    claim.record_event("ClaimStatusChanged", {"from": claim.status.value, "to": ClaimStatus.PAID.value})
    await repo.save(claim)
    return claim


# ── Dispute a claim ───────────────────────────────────────────────────────

class SubmitDisputeCommand:
    def __init__(
        self,
        claim_id: uuid.UUID,
        reason: str,
        line_item_id: Optional[uuid.UUID] = None,
    ) -> None:
        self.claim_id = claim_id
        self.reason = reason
        self.line_item_id = line_item_id


async def submit_dispute(cmd: SubmitDisputeCommand, session: AsyncSession) -> Dispute:
    claim_repo = ClaimRepository(session)
    dispute_repo = DisputeRepository(session)

    claim = await claim_repo.get(cmd.claim_id)
    if not claim:
        raise ClaimNotFound(f"Claim {cmd.claim_id} not found")

    # Transition claim to DISPUTED
    claim.status = transition_claim(claim.status, ClaimStatus.DISPUTED)

    dispute = Dispute(
        id=uuid.uuid4(),
        claim_id=cmd.claim_id,
        line_item_id=cmd.line_item_id,
        reason=cmd.reason,
        status=DisputeStatus.SUBMITTED,
        submitted_at=datetime.utcnow(),
    )

    claim.record_event("DisputeSubmitted", {
        "dispute_id": str(dispute.id),
        "line_item_id": str(cmd.line_item_id) if cmd.line_item_id else None,
    })

    await claim_repo.save(claim)
    await dispute_repo.save(dispute)
    logger.info("Dispute submitted for claim %s", claim.claim_number)
    return dispute


async def resolve_dispute(
    dispute_id: uuid.UUID,
    outcome: str,   # "UPHELD" | "DENIED"
    notes: str,
    session: AsyncSession,
) -> Dispute:
    dispute_repo = DisputeRepository(session)
    claim_repo = ClaimRepository(session)

    dispute = await dispute_repo.get(dispute_id)
    if not dispute:
        raise DisputeNotFound(f"Dispute {dispute_id} not found")

    # Transition dispute through UNDER_REVIEW → outcome
    dispute.status = transition_dispute(dispute.status, DisputeStatus.UNDER_REVIEW)
    outcome_status = DisputeStatus.UPHELD if outcome == "UPHELD" else DisputeStatus.DENIED
    dispute.resolve(outcome=outcome_status, notes=notes)
    await dispute_repo.save(dispute)

    # Transition claim to DISPUTE_RESOLVED
    claim = await claim_repo.get(dispute.claim_id)
    if claim:
        claim.status = transition_claim(claim.status, ClaimStatus.DISPUTE_RESOLVED)
        claim.record_event("DisputeResolved", {
            "dispute_id": str(dispute_id),
            "outcome": outcome,
        })
        await claim_repo.save(claim)

    return dispute


# ── Member & Policy management (minimal — not in scope) ──────────────────

async def create_member(
    member_id_str: str,
    name: str,
    date_of_birth: date,
    email: str,
    session: AsyncSession,
) -> Member:
    repo = MemberRepository(session)
    member = Member(
        id=uuid.uuid4(),
        member_id=member_id_str,
        name=name,
        date_of_birth=date_of_birth,
        email=email,
    )
    await repo.save(member)
    return member


async def create_policy(
    member_id: uuid.UUID,
    policy_number: str,
    effective_date: date,
    expiration_date: date,
    deductible_amount: str,
    out_of_pocket_max: str,
    coverage_rules: List[dict],
    session: AsyncSession,
) -> Policy:
    policy_repo = PolicyRepository(session)

    rules = []
    for r in coverage_rules:
        rule = CoverageRule(
            id=uuid.uuid4(),
            policy_id=uuid.uuid4(),  # will be overwritten below
            service_type=ServiceType(r["service_type"]),
            coverage_percentage=Decimal(str(r["coverage_percentage"])),
            annual_limit=Money.of(str(r["annual_limit"])) if r.get("annual_limit") else None,
            per_visit_limit=Money.of(str(r["per_visit_limit"])) if r.get("per_visit_limit") else None,
            copay=Money.of(str(r["copay"])) if r.get("copay") else None,
            requires_preauth=r.get("requires_preauth", False),
            network_restriction=NetworkType(r.get("network_restriction", "ANY")),
            excluded_diagnosis_codes=r.get("excluded_diagnosis_codes", []),
        )
        rules.append(rule)

    policy_id = uuid.uuid4()
    for rule in rules:
        object.__setattr__(rule, "policy_id", policy_id) if hasattr(rule, "__dataclass_fields__") else None
        rule.policy_id = policy_id

    policy = Policy(
        id=policy_id,
        member_id=member_id,
        policy_number=policy_number,
        effective_date=effective_date,
        expiration_date=expiration_date,
        status=PolicyStatus.ACTIVE,
        deductible_amount=Money.of(deductible_amount),
        deductible_met=Money.zero(),
        out_of_pocket_max=Money.of(out_of_pocket_max),
        coverage_rules=rules,
    )

    await policy_repo.save(policy)
    return policy
