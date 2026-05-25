"""
Repository implementations — the translation layer between ORM models and domain entities.

The repository pattern means the domain layer never imports SQLAlchemy.
Swap the DB tomorrow; domain tests stay green.

Pessimistic locking: AnnualUsageRepository.get_for_update() uses
SELECT FOR UPDATE to prevent concurrent claims from double-spending
an annual limit. The lock is held for the duration of the transaction.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claims.domain.entities import (
    AdjudicationResult,
    AnnualUsage,
    Claim,
    CoverageRule,
    Dispute,
    LineItem,
    Member,
    MembershipPolicy,
    Policy,
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

from .encryption import get_encryptor
from .models import (
    AdjudicationResultORM,
    AnnualUsageORM,
    ClaimORM,
    CoverageRuleORM,
    DisputeORM,
    DomainEventORM,
    LineItemORM,
    MemberORM,
    MembershipPolicyORM,
    PolicyORM,
)


# ── Mapping helpers ───────────────────────────────────────────────────────

def _money(value: Decimal | None) -> Optional[Money]:
    return Money(value) if value is not None else None


def _map_coverage_rule(orm: CoverageRuleORM) -> CoverageRule:
    return CoverageRule(
        id=orm.id,
        policy_id=orm.policy_id,
        service_type=ServiceType(orm.service_type),
        coverage_percentage=orm.coverage_percentage,
        annual_limit=_money(orm.annual_limit),
        per_visit_limit=_money(orm.per_visit_limit),
        copay=_money(orm.copay),
        requires_preauth=orm.requires_preauth,
        network_restriction=NetworkType(orm.network_restriction),
        excluded_diagnosis_codes=orm.excluded_diagnosis_codes or [],
    )


def _map_policy(orm: PolicyORM) -> Policy:
    return Policy(
        id=orm.id,
        holder_member_id=orm.holder_member_id,
        policy_number=orm.policy_number,
        effective_date=orm.effective_date,
        expiration_date=orm.expiration_date,
        status=PolicyStatus(orm.status),
        deductible_amount=Money(orm.deductible_amount),
        deductible_met=Money(orm.deductible_met),
        out_of_pocket_max=_money(orm.out_of_pocket_max),
        oop_used=Money(orm.oop_used) if orm.oop_used is not None else Money.zero(),
        coverage_rules=[_map_coverage_rule(r) for r in orm.coverage_rules],
    )


def _map_membership(orm: MembershipPolicyORM) -> MembershipPolicy:
    return MembershipPolicy(
        id=orm.id,
        policy_id=orm.policy_id,
        member_id=orm.member_id,
        relationship=orm.relationship,
        enrollment_date=orm.enrollment_date,
        termination_date=orm.termination_date,
        status=orm.status,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _map_adjudication(orm: AdjudicationResultORM) -> AdjudicationResult:
    return AdjudicationResult(
        id=orm.id,
        line_item_id=orm.line_item_id,
        covered_amount=Money(orm.covered_amount),
        denial_reason=DenialReason(orm.denial_reason) if orm.denial_reason else None,
        explanation=orm.explanation,
        adjudicated_at=orm.adjudicated_at,
        deductible_applied=Money(orm.deductible_applied),
        copay_applied=Money(orm.copay_applied),
        applied_rule_id=orm.applied_rule_id,
    )


def _map_line_item(orm: LineItemORM) -> LineItem:
    enc = get_encryptor()
    li = LineItem.__new__(LineItem)  # bypass __post_init__ validation for DB round-trip
    li.id = orm.id
    li.claim_id = orm.claim_id
    li.service_type = ServiceType(orm.service_type)
    li.service_date = orm.service_date
    li.billed_amount = Money(orm.billed_amount)
    li.diagnosis_code = enc.decrypt(orm.phi_diagnosis_code)
    li.procedure_code = orm.procedure_code
    li.description = orm.description
    li.status = LineItemStatus(orm.status)
    li.adjudication = _map_adjudication(orm.adjudication) if orm.adjudication else None
    return li


def _map_member(orm: MemberORM) -> Member:
    enc = get_encryptor()
    from datetime import date as date_type
    # Collect all policies this member is enrolled in (as holder or dependent)
    # orm.memberships is selectin-loaded; each membership carries its policy via join
    policies = [
        _map_policy(m.policy)
        for m in orm.memberships
        if m.policy is not None
    ]
    return Member(
        id=orm.id,
        member_id=enc.decrypt(orm.phi_member_id),
        name=enc.decrypt(orm.phi_name),
        date_of_birth=date_type.fromisoformat(enc.decrypt(orm.phi_date_of_birth)),
        email=enc.decrypt(orm.phi_email),
        policies=policies,
    )


def _map_claim(orm: ClaimORM) -> Claim:
    return Claim(
        id=orm.id,
        claim_number=orm.claim_number,
        member_id=orm.member_id,
        policy_id=orm.policy_id,
        status=ClaimStatus(orm.status),
        submitted_at=orm.submitted_at,
        provider_name=orm.provider_name,
        provider_npi=orm.provider_npi,
        line_items=[_map_line_item(li) for li in orm.line_items],
        events=[],
        updated_at=orm.updated_at,
    )


def _map_dispute(orm: DisputeORM) -> Dispute:
    return Dispute(
        id=orm.id,
        claim_id=orm.claim_id,
        line_item_id=orm.line_item_id,
        reason=orm.reason,
        status=DisputeStatus(orm.status),
        submitted_at=orm.submitted_at,
        resolved_at=orm.resolved_at,
        resolution_notes=orm.resolution_notes,
    )


# ── Repositories ──────────────────────────────────────────────────────────

class MemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, member_id: uuid.UUID) -> Optional[Member]:
        result = await self._session.get(MemberORM, member_id)
        return _map_member(result) if result else None

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Member]:
        stmt = select(MemberORM).order_by(MemberORM.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_map_member(m) for m in result.scalars().all()]

    async def count(self) -> int:
        from sqlalchemy import func as sqlfunc
        result = await self._session.execute(select(sqlfunc.count(MemberORM.id)))
        return result.scalar_one()

    async def save(self, member: Member) -> None:
        enc = get_encryptor()
        existing = await self._session.get(MemberORM, member.id)
        if existing:
            existing.phi_member_id = enc.encrypt(member.member_id)
            existing.phi_name = enc.encrypt(member.name)
            existing.phi_date_of_birth = enc.encrypt(member.date_of_birth.isoformat())
            existing.phi_email = enc.encrypt(member.email)
        else:
            orm = MemberORM(
                id=member.id,
                phi_member_id=enc.encrypt(member.member_id),
                phi_name=enc.encrypt(member.name),
                phi_date_of_birth=enc.encrypt(member.date_of_birth.isoformat()),
                phi_email=enc.encrypt(member.email),
            )
            self._session.add(orm)


class PolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, policy_id: uuid.UUID) -> Optional[Policy]:
        result = await self._session.get(PolicyORM, policy_id)
        return _map_policy(result) if result else None

    async def get_by_member(self, member_id: uuid.UUID) -> List[Policy]:
        """
        Return all policies the member is enrolled in — as holder OR dependent.
        Queries via membership_policies so dependents see their coverage too.
        Only returns policies with an ACTIVE membership row for this member.
        """
        stmt = (
            select(PolicyORM)
            .join(MembershipPolicyORM, MembershipPolicyORM.policy_id == PolicyORM.id)
            .where(MembershipPolicyORM.member_id == member_id)
            .where(MembershipPolicyORM.status == "ACTIVE")
        )
        result = await self._session.execute(stmt)
        return [_map_policy(p) for p in result.scalars().all()]

    async def get_by_holder(self, holder_member_id: uuid.UUID) -> List[Policy]:
        """Return policies where this member is the primary subscriber (contract holder)."""
        stmt = select(PolicyORM).where(PolicyORM.holder_member_id == holder_member_id)
        result = await self._session.execute(stmt)
        return [_map_policy(p) for p in result.scalars().all()]

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Policy]:
        stmt = select(PolicyORM).order_by(PolicyORM.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_map_policy(p) for p in result.scalars().all()]

    async def count(self) -> int:
        from sqlalchemy import func as sqlfunc
        result = await self._session.execute(select(sqlfunc.count(PolicyORM.id)))
        return result.scalar_one()

    async def count_active(self) -> int:
        from sqlalchemy import func as sqlfunc
        result = await self._session.execute(
            select(sqlfunc.count(PolicyORM.id)).where(PolicyORM.status == "ACTIVE")
        )
        return result.scalar_one()

    async def save(self, policy: Policy) -> None:
        existing = await self._session.get(PolicyORM, policy.id)
        if existing:
            existing.deductible_met = policy.deductible_met.amount
            existing.oop_used = policy.oop_used.amount
            existing.status = policy.status.value
        else:
            orm = PolicyORM(
                id=policy.id,
                holder_member_id=policy.holder_member_id,
                policy_number=policy.policy_number,
                effective_date=policy.effective_date,
                expiration_date=policy.expiration_date,
                status=policy.status.value,
                deductible_amount=policy.deductible_amount.amount,
                deductible_met=policy.deductible_met.amount,
                out_of_pocket_max=policy.out_of_pocket_max.amount if policy.out_of_pocket_max else None,
                oop_used=policy.oop_used.amount,
            )
            self._session.add(orm)
            for rule in policy.coverage_rules:
                rule_orm = CoverageRuleORM(
                    id=rule.id,
                    policy_id=policy.id,
                    service_type=rule.service_type.value,
                    coverage_percentage=rule.coverage_percentage,
                    annual_limit=rule.annual_limit.amount if rule.annual_limit else None,
                    per_visit_limit=rule.per_visit_limit.amount if rule.per_visit_limit else None,
                    copay=rule.copay.amount if rule.copay else None,
                    requires_preauth=rule.requires_preauth,
                    network_restriction=rule.network_restriction.value,
                    excluded_diagnosis_codes=rule.excluded_diagnosis_codes,
                )
                self._session.add(rule_orm)


class MembershipPolicyRepository:
    """
    Manages member enrollment records under a policy.

    Key invariants:
      - The primary subscriber always has a SELF enrollment row (created by
        PolicyRepository.save via the application service).
      - A member can only be enrolled once per policy (UNIQUE constraint).
      - Terminating a membership sets status=TERMINATED + termination_date;
        the row is never deleted so the audit trail is preserved.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, membership_id: uuid.UUID) -> Optional[MembershipPolicy]:
        result = await self._session.get(MembershipPolicyORM, membership_id)
        return _map_membership(result) if result else None

    async def get_by_policy_and_member(
        self, policy_id: uuid.UUID, member_id: uuid.UUID
    ) -> Optional[MembershipPolicy]:
        stmt = select(MembershipPolicyORM).where(
            MembershipPolicyORM.policy_id == policy_id,
            MembershipPolicyORM.member_id == member_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _map_membership(orm) if orm else None

    async def has_active_membership(
        self, policy_id: uuid.UUID, member_id: uuid.UUID
    ) -> bool:
        """
        Fast boolean check — used at claim submission to guard against a member
        submitting a claim against a policy they are not (or no longer) enrolled in.
        Hits ix_membership_policies_member_active partial index.
        """
        stmt = select(MembershipPolicyORM.id).where(
            MembershipPolicyORM.policy_id == policy_id,
            MembershipPolicyORM.member_id == member_id,
            MembershipPolicyORM.status == "ACTIVE",
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_by_policy(self, policy_id: uuid.UUID) -> List[MembershipPolicy]:
        stmt = select(MembershipPolicyORM).where(
            MembershipPolicyORM.policy_id == policy_id,
        ).order_by(MembershipPolicyORM.enrollment_date)
        result = await self._session.execute(stmt)
        return [_map_membership(m) for m in result.scalars().all()]

    async def list_active_by_policy(self, policy_id: uuid.UUID) -> List[MembershipPolicy]:
        stmt = select(MembershipPolicyORM).where(
            MembershipPolicyORM.policy_id == policy_id,
            MembershipPolicyORM.status == "ACTIVE",
        ).order_by(MembershipPolicyORM.enrollment_date)
        result = await self._session.execute(stmt)
        return [_map_membership(m) for m in result.scalars().all()]

    async def save(self, membership: MembershipPolicy) -> None:
        existing = await self._session.get(MembershipPolicyORM, membership.id)
        if existing:
            existing.status = membership.status
            existing.termination_date = membership.termination_date
            existing.updated_at = membership.updated_at
        else:
            orm = MembershipPolicyORM(
                id=membership.id,
                policy_id=membership.policy_id,
                member_id=membership.member_id,
                relationship=membership.relationship,
                enrollment_date=membership.enrollment_date,
                termination_date=membership.termination_date,
                status=membership.status,
            )
            self._session.add(orm)


class AnnualUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        policy_id: uuid.UUID,
        service_type: ServiceType,
        benefit_year: int,
    ) -> Optional[AnnualUsage]:
        stmt = select(AnnualUsageORM).where(
            AnnualUsageORM.policy_id == policy_id,
            AnnualUsageORM.service_type == service_type.value,
            AnnualUsageORM.benefit_year == benefit_year,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return AnnualUsage(
            id=orm.id,
            policy_id=orm.policy_id,
            service_type=ServiceType(orm.service_type),
            benefit_year=orm.benefit_year,
            used_amount=Money(orm.used_amount),
        )

    async def get_for_update(
        self,
        policy_id: uuid.UUID,
        service_type: ServiceType,
        benefit_year: int,
    ) -> Optional[AnnualUsageORM]:
        """
        SELECT FOR UPDATE — acquires a row-level lock for the duration of
        the current transaction. Prevents concurrent adjudications from
        double-spending an annual limit.
        """
        stmt = (
            select(AnnualUsageORM)
            .where(
                AnnualUsageORM.policy_id == policy_id,
                AnnualUsageORM.service_type == service_type.value,
                AnnualUsageORM.benefit_year == benefit_year,
            )
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, usage: AnnualUsage) -> None:
        existing = await self._session.get(AnnualUsageORM, usage.id)
        if existing:
            existing.used_amount = usage.used_amount.amount
        else:
            orm = AnnualUsageORM(
                id=usage.id,
                policy_id=usage.policy_id,
                service_type=usage.service_type.value,
                benefit_year=usage.benefit_year,
                used_amount=usage.used_amount.amount,
            )
            self._session.add(orm)


class ClaimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, claim_id: uuid.UUID) -> Optional[Claim]:
        result = await self._session.get(ClaimORM, claim_id)
        return _map_claim(result) if result else None

    async def get_by_number(self, claim_number: str) -> Optional[Claim]:
        stmt = select(ClaimORM).where(ClaimORM.claim_number == claim_number)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _map_claim(orm) if orm else None

    async def list_by_member(self, member_id: uuid.UUID) -> List[Claim]:
        stmt = select(ClaimORM).where(ClaimORM.member_id == member_id).order_by(ClaimORM.submitted_at.desc())
        result = await self._session.execute(stmt)
        return [_map_claim(c) for c in result.scalars().all()]

    async def list_all(self, limit: int = 50, offset: int = 0) -> List[Claim]:
        stmt = select(ClaimORM).order_by(ClaimORM.submitted_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [_map_claim(c) for c in result.scalars().all()]

    async def list_by_provider_npi(self, provider_npi: str, limit: int = 50, offset: int = 0) -> List[Claim]:
        stmt = (
            select(ClaimORM)
            .where(ClaimORM.provider_npi == provider_npi)
            .order_by(ClaimORM.submitted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_map_claim(c) for c in result.scalars().all()]

    async def save(self, claim: Claim) -> None:
        enc = get_encryptor()
        existing = await self._session.get(ClaimORM, claim.id)
        if existing:
            existing.status = claim.status.value
            existing.updated_at = datetime.utcnow()
        else:
            orm = ClaimORM(
                id=claim.id,
                claim_number=claim.claim_number,
                member_id=claim.member_id,
                policy_id=claim.policy_id,
                status=claim.status.value,
                submitted_at=claim.submitted_at,
                provider_name=claim.provider_name,
                provider_npi=claim.provider_npi,
            )
            self._session.add(orm)

        for li in claim.line_items:
            existing_li = await self._session.get(LineItemORM, li.id)
            if existing_li:
                existing_li.status = li.status.value
            else:
                li_orm = LineItemORM(
                    id=li.id,
                    claim_id=claim.id,
                    service_type=li.service_type.value,
                    service_date=li.service_date,
                    billed_amount=li.billed_amount.amount,
                    phi_diagnosis_code=enc.encrypt(li.diagnosis_code),
                    procedure_code=li.procedure_code,
                    description=li.description,
                    status=li.status.value,
                )
                self._session.add(li_orm)

            if li.adjudication:
                adj = li.adjudication
                existing_adj = await self._session.get(AdjudicationResultORM, adj.id)
                if not existing_adj:
                    adj_orm = AdjudicationResultORM(
                        id=adj.id,
                        line_item_id=li.id,
                        covered_amount=adj.covered_amount.amount,
                        denial_reason=adj.denial_reason.value if adj.denial_reason else None,
                        explanation=adj.explanation,
                        adjudicated_at=adj.adjudicated_at,
                        deductible_applied=adj.deductible_applied.amount,
                        copay_applied=adj.copay_applied.amount,
                        applied_rule_id=adj.applied_rule_id,
                    )
                    self._session.add(adj_orm)

        for event in claim.events:
            event_orm = DomainEventORM(
                id=uuid.uuid4(),
                claim_id=claim.id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                payload=event.payload,
            )
            self._session.add(event_orm)
        claim.events.clear()


class DisputeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, dispute_id: uuid.UUID) -> Optional[Dispute]:
        result = await self._session.get(DisputeORM, dispute_id)
        return _map_dispute(result) if result else None

    async def list_by_claim(self, claim_id: uuid.UUID) -> List[Dispute]:
        stmt = select(DisputeORM).where(DisputeORM.claim_id == claim_id)
        result = await self._session.execute(stmt)
        return [_map_dispute(d) for d in result.scalars().all()]

    async def save(self, dispute: Dispute) -> None:
        existing = await self._session.get(DisputeORM, dispute.id)
        if existing:
            existing.status = dispute.status.value
            existing.resolved_at = dispute.resolved_at
            existing.resolution_notes = dispute.resolution_notes
        else:
            orm = DisputeORM(
                id=dispute.id,
                claim_id=dispute.claim_id,
                line_item_id=dispute.line_item_id,
                reason=dispute.reason,
                status=dispute.status.value,
                submitted_at=dispute.submitted_at,
            )
            self._session.add(orm)
