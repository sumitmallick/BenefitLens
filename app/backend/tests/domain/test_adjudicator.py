"""
Adjudicator tests — the most domain-rich tests in the system.

Each test describes a real-world scenario:
  "when a member with a $500 deductible submits a specialist claim..."

These tests drove the adjudicator implementation (written first).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

import pytest

from claims.domain.adjudicator import AdjudicationContext, adjudicate
from claims.domain.entities import (
    AnnualUsage,
    CoverageRule,
    LineItem,
    Policy,
)
from claims.domain.value_objects import (
    ClaimStatus,
    DenialReason,
    LineItemStatus,
    Money,
    NetworkType,
    PolicyStatus,
    ServiceType,
)


TODAY = date.today()
BENEFIT_YEAR = TODAY.year


# ── Fixtures ──────────────────────────────────────────────────────────────

def make_policy(
    deductible: str = "500.00",
    deductible_met: str = "0.00",
    effective: date = date(BENEFIT_YEAR, 1, 1),
    expiration: date = date(BENEFIT_YEAR, 12, 31),
    status: PolicyStatus = PolicyStatus.ACTIVE,
) -> Policy:
    return Policy(
        id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        policy_number="POL-TEST-001",
        effective_date=effective,
        expiration_date=expiration,
        status=status,
        deductible_amount=Money.of(deductible),
        deductible_met=Money.of(deductible_met),
        out_of_pocket_max=Money.of("5000.00"),
        coverage_rules=[],
    )


def make_rule(
    policy: Policy,
    service_type: ServiceType = ServiceType.SPECIALIST_VISIT,
    coverage_pct: str = "80",
    annual_limit: Optional[str] = "2000.00",
    per_visit_limit: Optional[str] = "300.00",
    copay: Optional[str] = "30.00",
    requires_preauth: bool = False,
    excluded_dx: Optional[List[str]] = None,
) -> CoverageRule:
    rule = CoverageRule(
        id=uuid.uuid4(),
        policy_id=policy.id,
        service_type=service_type,
        coverage_percentage=Decimal(coverage_pct),
        annual_limit=Money.of(annual_limit) if annual_limit else None,
        per_visit_limit=Money.of(per_visit_limit) if per_visit_limit else None,
        copay=Money.of(copay) if copay else None,
        requires_preauth=requires_preauth,
        network_restriction=NetworkType.ANY,
        excluded_diagnosis_codes=excluded_dx or [],
    )
    policy.coverage_rules.append(rule)
    return rule


def make_line_item(
    service_type: ServiceType = ServiceType.SPECIALIST_VISIT,
    billed: str = "250.00",
    service_date: Optional[date] = None,
    diagnosis: str = "M54.5",     # Low back pain
    procedure: str = "99213",
) -> LineItem:
    claim_id = uuid.uuid4()
    return LineItem(
        id=uuid.uuid4(),
        claim_id=claim_id,
        service_type=service_type,
        service_date=service_date or TODAY,
        billed_amount=Money.of(billed),
        diagnosis_code=diagnosis,
        procedure_code=procedure,
        description="Office visit",
    )


def make_usage(policy: Policy, service_type: ServiceType, used: str = "0.00") -> AnnualUsage:
    return AnnualUsage(
        id=uuid.uuid4(),
        policy_id=policy.id,
        service_type=service_type,
        benefit_year=BENEFIT_YEAR,
        used_amount=Money.of(used),
    )


# ── Basic approval scenarios ──────────────────────────────────────────────

class TestBasicApproval:
    def test_covered_service_within_limits_is_partially_covered(self):
        """
        $250 specialist visit.
        Deductible: $500 (none met).
        → deductible eats $250, no remainder → covered_amount = $0? No:
        After deductible apply: remainder = 0, copay on 0 = 0, 80% of 0 = 0 → DENIED.

        Wait — the test documents intent: a $250 bill where the full amount goes to
        deductible results in $0 covered. That's correct behavior.
        """
        policy = make_policy(deductible="500.00", deductible_met="0.00")
        make_rule(policy, copay=None, coverage_pct="80", per_visit_limit=None)
        line_item = make_line_item(billed="250.00")
        usage = make_usage(policy, ServiceType.SPECIALIST_VISIT)
        ctx = AdjudicationContext(policy=policy, annual_usage=usage)

        result_li, _ = adjudicate(line_item, ctx)

        # Deductible consumed the entire $250; coverage pays nothing
        assert result_li.adjudication.covered_amount == Money.zero()
        assert result_li.adjudication.deductible_applied == Money.of("250.00")
        assert result_li.status == LineItemStatus.DENIED

    def test_deductible_fully_met_service_is_covered(self):
        """
        $250 specialist visit, $500 deductible already fully met.
        No copay. 80% coverage.
        → covered = $250 * 0.80 = $200
        """
        policy = make_policy(deductible="500.00", deductible_met="500.00")
        make_rule(policy, copay=None, coverage_pct="80", per_visit_limit=None, annual_limit=None)
        line_item = make_line_item(billed="250.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.adjudication.covered_amount == Money.of("200.00")
        assert result_li.adjudication.deductible_applied == Money.zero()
        assert result_li.status == LineItemStatus.PARTIALLY_COVERED

    def test_100_percent_coverage_no_deductible_is_fully_covered(self):
        """Preventive visit: 100% coverage, no deductible."""
        policy = make_policy(deductible="500.00", deductible_met="0.00")
        make_rule(
            policy,
            service_type=ServiceType.PREVENTIVE,
            copay=None,
            coverage_pct="100",
            per_visit_limit=None,
            annual_limit=None,
        )
        line_item = make_line_item(
            service_type=ServiceType.PREVENTIVE,
            billed="150.00",
            diagnosis="Z00.00",   # General adult medical exam
            procedure="99395",
        )
        # Preventive bypasses deductible
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.COVERED
        assert result_li.adjudication.covered_amount == Money.of("150.00")
        assert result_li.adjudication.deductible_applied == Money.zero()


# ── Denial scenarios ──────────────────────────────────────────────────────

class TestDenials:
    def test_service_not_in_policy_is_denied(self):
        """Dental claim on a policy with no dental coverage."""
        policy = make_policy()
        # Only specialist rule, no dental
        make_rule(policy, service_type=ServiceType.SPECIALIST_VISIT)
        line_item = make_line_item(
            service_type=ServiceType.DENTAL,
            diagnosis="K02.9",
            procedure="D0120",
        )
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.DENIED
        assert result_li.adjudication.denial_reason == DenialReason.NOT_COVERED_SERVICE
        assert "not covered" in result_li.adjudication.explanation.lower()

    def test_service_outside_policy_period_is_denied(self):
        """Claim for a date before the policy effective date."""
        policy = make_policy(
            effective=date(BENEFIT_YEAR, 6, 1),
            expiration=date(BENEFIT_YEAR, 12, 31),
        )
        make_rule(policy)
        line_item = make_line_item(service_date=date(BENEFIT_YEAR, 1, 15))
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.DENIED
        assert result_li.adjudication.denial_reason == DenialReason.SERVICE_DATE_OUT_OF_POLICY_PERIOD

    def test_inactive_policy_denies_all(self):
        policy = make_policy(status=PolicyStatus.INACTIVE)
        make_rule(policy)
        line_item = make_line_item()
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.DENIED
        assert result_li.adjudication.denial_reason == DenialReason.SERVICE_DATE_OUT_OF_POLICY_PERIOD

    def test_excluded_diagnosis_code_is_denied(self):
        """Service type is covered but the specific diagnosis is excluded."""
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, excluded_dx=["M54.5"])
        line_item = make_line_item(diagnosis="M54.5")   # back pain — excluded
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.DENIED
        assert result_li.adjudication.denial_reason == DenialReason.EXCLUDED_DIAGNOSIS

    def test_requires_preauth_without_auth_is_denied(self):
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, requires_preauth=True)
        line_item = make_line_item()
        ctx = AdjudicationContext(policy=policy, annual_usage=None, preauth_granted=False)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.DENIED
        assert result_li.adjudication.denial_reason == DenialReason.REQUIRES_PREAUTH

    def test_preauth_granted_allows_adjudication_to_proceed(self):
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, requires_preauth=True, copay=None, per_visit_limit=None, annual_limit=None)
        line_item = make_line_item(billed="300.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=None, preauth_granted=True)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status != LineItemStatus.DENIED or (
            result_li.adjudication.denial_reason != DenialReason.REQUIRES_PREAUTH
        )


# ── Annual limit scenarios ────────────────────────────────────────────────

class TestAnnualLimits:
    def test_annual_limit_exhausted_denies_claim(self):
        """Member has used their full $2,000 annual benefit."""
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, annual_limit="2000.00", copay=None)
        line_item = make_line_item(billed="200.00")
        usage = make_usage(policy, ServiceType.SPECIALIST_VISIT, used="2000.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=usage)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.status == LineItemStatus.DENIED
        assert result_li.adjudication.denial_reason == DenialReason.ANNUAL_LIMIT_EXHAUSTED

    def test_partial_annual_limit_reduces_covered_amount(self):
        """Member has $150 left of their annual benefit; bills $300."""
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, annual_limit="2000.00", copay=None, per_visit_limit=None, coverage_pct="100")
        line_item = make_line_item(billed="300.00")
        usage = make_usage(policy, ServiceType.SPECIALIST_VISIT, used="1850.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=usage)

        result_li, updated_usage = adjudicate(line_item, ctx)

        # Only $150 remaining; 100% coverage → $150 covered
        assert result_li.adjudication.covered_amount == Money.of("150.00")
        assert result_li.status == LineItemStatus.PARTIALLY_COVERED
        # Usage should now be at $2000
        assert updated_usage.used_amount == Money.of("2000.00")

    def test_annual_usage_accumulates_correctly(self):
        """Two claims in the same year; second is capped by remaining limit."""
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, annual_limit="1000.00", copay=None, per_visit_limit=None, coverage_pct="100")

        usage = make_usage(policy, ServiceType.SPECIALIST_VISIT, used="0.00")

        li1 = make_line_item(billed="600.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=usage)
        li1, usage = adjudicate(li1, ctx)
        assert li1.adjudication.covered_amount == Money.of("600.00")
        assert usage.used_amount == Money.of("600.00")

        li2 = make_line_item(billed="600.00")
        ctx2 = AdjudicationContext(policy=policy, annual_usage=usage)
        li2, usage = adjudicate(li2, ctx2)
        # Only $400 remaining
        assert li2.adjudication.covered_amount == Money.of("400.00")
        assert usage.used_amount == Money.of("1000.00")


# ── Per-visit limit ───────────────────────────────────────────────────────

class TestPerVisitLimit:
    def test_billed_above_per_visit_limit_is_capped(self):
        """
        $500 billed; $300 per-visit cap; deductible met; 80% coverage; no copay.
        → payable capped at $300
        → covered = $300 * 0.80 = $240
        """
        policy = make_policy(deductible_met="500.00")
        make_rule(
            policy,
            coverage_pct="80",
            per_visit_limit="300.00",
            copay=None,
            annual_limit=None,
        )
        line_item = make_line_item(billed="500.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.adjudication.covered_amount == Money.of("240.00")
        assert result_li.status == LineItemStatus.PARTIALLY_COVERED


# ── Copay ─────────────────────────────────────────────────────────────────

class TestCopay:
    def test_copay_is_subtracted_before_coverage_percentage(self):
        """
        $250 billed; deductible met; $30 copay; 80% coverage; no caps.
        → after copay: $220 → 80% = $176
        """
        policy = make_policy(deductible_met="500.00")
        make_rule(
            policy,
            coverage_pct="80",
            copay="30.00",
            per_visit_limit=None,
            annual_limit=None,
        )
        line_item = make_line_item(billed="250.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert result_li.adjudication.copay_applied == Money.of("30.00")
        assert result_li.adjudication.covered_amount == Money.of("176.00")

    def test_explanation_mentions_copay(self):
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, copay="30.00", per_visit_limit=None, annual_limit=None)
        line_item = make_line_item(billed="250.00")
        ctx = AdjudicationContext(policy=policy, annual_usage=None)

        result_li, _ = adjudicate(line_item, ctx)

        assert "copay" in result_li.adjudication.explanation.lower()


# ── Explanation quality ───────────────────────────────────────────────────

class TestExplanations:
    def test_denial_explanation_names_the_policy(self):
        policy = make_policy()
        # No rules for DENTAL
        line_item = make_line_item(
            service_type=ServiceType.DENTAL, diagnosis="K02.9", procedure="D0120"
        )
        ctx = AdjudicationContext(policy=policy, annual_usage=None)
        result_li, _ = adjudicate(line_item, ctx)

        assert "POL-TEST-001" in result_li.adjudication.explanation

    def test_annual_limit_denial_mentions_limit_amount(self):
        policy = make_policy(deductible_met="500.00")
        make_rule(policy, annual_limit="2000.00")
        usage = make_usage(policy, ServiceType.SPECIALIST_VISIT, used="2000.00")
        line_item = make_line_item()
        ctx = AdjudicationContext(policy=policy, annual_usage=usage)

        result_li, _ = adjudicate(line_item, ctx)

        assert "2000" in result_li.adjudication.explanation


# ── Value object tests ────────────────────────────────────────────────────

class TestMoney:
    def test_money_addition(self):
        assert Money.of("100.00") + Money.of("50.00") == Money.of("150.00")

    def test_money_subtraction_floors_at_zero(self):
        assert Money.of("30.00") - Money.of("100.00") == Money.zero()

    def test_money_multiplication(self):
        assert Money.of("200.00") * Decimal("0.80") == Money.of("160.00")

    def test_money_cannot_be_negative(self):
        with pytest.raises(ValueError):
            Money(amount=Decimal("-1.00"))

    def test_money_rounds_to_two_decimal_places(self):
        m = Money.of("100.005")
        assert str(m.amount) in {"100.00", "100.01"}  # banker's rounding

    def test_money_zero(self):
        assert Money.zero().is_zero is True


class TestDiagnosisCode:
    def test_valid_icd10_with_decimal(self):
        from claims.domain.value_objects import DiagnosisCode
        code = DiagnosisCode("M54.5")
        assert code.code == "M54.5"

    def test_valid_icd10_without_decimal_subcode(self):
        from claims.domain.value_objects import DiagnosisCode
        code = DiagnosisCode("Z00.00")
        assert code.code == "Z00.00"

    def test_invalid_format_raises(self):
        from claims.domain.value_objects import DiagnosisCode
        with pytest.raises(ValueError):
            DiagnosisCode("NOTACODE")
