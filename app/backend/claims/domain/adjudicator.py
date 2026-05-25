"""
The adjudication engine — the heart of the system.

Given a LineItem and its Policy (with CoverageRules + AnnualUsage), the
adjudicator determines:
  1. Is the service type covered at all?
  2. Is the policy active on the service date?
  3. Is the diagnosis code excluded?
  4. Does preauth apply?
  5. How much of the annual limit remains?
  6. Apply deductible, copay, coverage percentage, per-visit limit.
  7. Return an AdjudicationResult with a plain-English explanation.

The adjudicator is a pure function (no I/O, no side effects).
The application service is responsible for:
  - loading Policy + AnnualUsage from the DB
  - committing the AdjudicationResult + updated AnnualUsage
  - publishing domain events

This purity makes the adjudicator straightforward to unit-test
and replayable from an event log.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .entities import AdjudicationResult, AnnualUsage, LineItem, Policy
from .value_objects import (
    DenialReason,
    DiagnosisCode,
    LineItemStatus,
    Money,
)


class AdjudicationError(Exception):
    """Raised when adjudication cannot proceed due to missing data."""


class AdjudicationContext:
    """
    All data the adjudicator needs to make a decision.
    Assembled by the application service before calling adjudicate().
    """
    __slots__ = ("policy", "annual_usage", "preauth_granted")

    def __init__(
        self,
        policy: Policy,
        annual_usage: Optional[AnnualUsage],
        preauth_granted: bool = False,
    ) -> None:
        self.policy = policy
        self.annual_usage = annual_usage
        self.preauth_granted = preauth_granted


def adjudicate(line_item: LineItem, ctx: AdjudicationContext) -> tuple[LineItem, AnnualUsage | None]:
    """
    Core adjudication logic. Returns:
      - the mutated line_item (status + adjudication set)
      - an updated AnnualUsage object (or None if no limit applies)

    Caller is responsible for persisting both.

    Decision sequence (mirrors real-world claim adjudication order):
      Step 1  Policy active on service date?
      Step 2  Service type covered?
      Step 3  Diagnosis code excluded under this rule?
      Step 4  Preauth required but not granted?
      Step 5  Annual limit exhausted?
      Step 6  Per-visit limit check (soft cap — partial approval)
      Step 7  Deductible application
      Step 8  Copay
      Step 9  Apply coverage percentage to remainder
      Step 10 Build explanation
    """
    policy = ctx.policy
    result_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # ── Step 1: Policy active? ──────────────────────────────────────────
    if not policy.is_active_on(line_item.service_date):
        return _deny(
            line_item,
            result_id,
            now,
            DenialReason.SERVICE_DATE_OUT_OF_POLICY_PERIOD,
            (
                f"Your policy #{policy.policy_number} was not active on "
                f"{line_item.service_date.isoformat()}. "
                f"Policy period: {policy.effective_date} to {policy.expiration_date}."
            ),
        ), None

    # ── Step 2: Service covered? ────────────────────────────────────────
    rule = policy.rule_for(line_item.service_type)
    if rule is None:
        return _deny(
            line_item,
            result_id,
            now,
            DenialReason.NOT_COVERED_SERVICE,
            (
                f"Service type '{line_item.service_type.value}' is not covered "
                f"under policy #{policy.policy_number}."
            ),
        ), None

    # ── Step 3: Diagnosis excluded? ─────────────────────────────────────
    diag = line_item.diagnosis_code.upper()
    if rule.excluded_diagnosis_codes and diag in [d.upper() for d in rule.excluded_diagnosis_codes]:
        return _deny(
            line_item,
            result_id,
            now,
            DenialReason.EXCLUDED_DIAGNOSIS,
            (
                f"Diagnosis code {diag} is excluded from coverage under "
                f"service type '{line_item.service_type.value}' in your policy."
            ),
        ), None

    # ── Step 4: Preauth? ────────────────────────────────────────────────
    if rule.requires_preauth and not ctx.preauth_granted:
        return _deny(
            line_item,
            result_id,
            now,
            DenialReason.REQUIRES_PREAUTH,
            (
                f"Service type '{line_item.service_type.value}' requires prior "
                f"authorization. No pre-authorization was found for this claim."
            ),
        ), None

    # ── Step 5: Annual limit ────────────────────────────────────────────
    annual_usage = ctx.annual_usage
    if rule.annual_limit is not None:
        if annual_usage is None:
            # No usage record yet; create a zero-usage entry
            annual_usage = AnnualUsage(
                id=uuid.uuid4(),
                policy_id=policy.id,
                service_type=rule.service_type,
                benefit_year=line_item.service_date.year,
                used_amount=Money.zero(),
            )

        remaining = annual_usage.remaining(rule.annual_limit)
        if remaining is not None and remaining.is_zero:
            return _deny(
                line_item,
                result_id,
                now,
                DenialReason.ANNUAL_LIMIT_EXHAUSTED,
                (
                    f"Your annual benefit limit of {rule.annual_limit} for "
                    f"'{line_item.service_type.value}' has been fully used for "
                    f"benefit year {line_item.service_date.year}."
                ),
            ), annual_usage

    # ── Steps 6-9: Amount calculation ──────────────────────────────────

    # Start with billed amount; clamp to per-visit limit
    payable = line_item.billed_amount
    per_visit_capped = False

    if rule.per_visit_limit is not None and payable > rule.per_visit_limit:
        payable = rule.per_visit_limit
        per_visit_capped = True

    # Clamp to remaining annual allowance
    annual_capped = False
    if rule.annual_limit is not None and annual_usage is not None:
        remaining = annual_usage.remaining(rule.annual_limit)
        if remaining is not None and payable > remaining:
            payable = remaining
            annual_capped = True

    # Deductible applies (we mutate policy.deductible_met)
    deductible_applied = Money.zero()
    deductible_applies = rule.service_type.value != "PREVENTIVE"  # preventive bypasses deductible
    if deductible_applies and not policy.remaining_deductible.is_zero:
        deductible_applied, payable = policy.apply_deductible(payable)

    # Copay
    copay_applied = Money.zero()
    if rule.copay is not None and not payable.is_zero:
        copay_applied = rule.copay
        payable = payable - copay_applied
        if payable.is_zero:
            # Copay ate everything
            payable = Money.zero()

    # Coverage percentage
    covered = payable * rule.coverage_factor

    # ── Step 9.5: Out-of-pocket maximum ────────────────────────────────
    # member_cost_sharing = deductible + copay + coinsurance (member's share)
    # coinsurance = payable_after_copay - covered  (i.e. payable * (1 - coverage_factor))
    coinsurance = payable - covered  # payable here is already after deductible and copay
    member_cost_sharing = deductible_applied + copay_applied + coinsurance
    _, oop_subsidy = policy.apply_oop_max(member_cost_sharing)

    if not oop_subsidy.is_zero:
        # OOP max hit — insurer covers the excess coinsurance
        covered = covered + oop_subsidy

    # Consume annual usage
    if annual_usage is not None and not covered.is_zero:
        annual_usage.consume(covered)

    # ── Step 10: Explanation ────────────────────────────────────────────
    explanation_parts = [
        f"Billed amount: {line_item.billed_amount}.",
    ]
    if per_visit_capped:
        explanation_parts.append(
            f"Per-visit limit applied: {rule.per_visit_limit}."
        )
    if annual_capped:
        explanation_parts.append(
            f"Amount reduced to remaining annual benefit: {payable + deductible_applied + copay_applied}."
        )
    if not deductible_applied.is_zero:
        explanation_parts.append(
            f"Deductible applied: {deductible_applied} "
            f"(annual deductible: {policy.deductible_amount})."
        )
    if not copay_applied.is_zero:
        explanation_parts.append(f"Copay: {copay_applied}.")
    explanation_parts.append(
        f"Coverage at {rule.coverage_percentage}%: {covered}."
    )
    if not oop_subsidy.is_zero:
        explanation_parts.append(
            f"Out-of-pocket maximum of {policy.out_of_pocket_max} reached; "
            f"plan covered additional {oop_subsidy}."
        )

    # Determine line item status
    if covered.is_zero:
        status = LineItemStatus.DENIED
        denial = DenialReason.ANNUAL_LIMIT_EXHAUSTED if annual_capped else None
        explanation_parts.append("No benefit payable after applying all cost-sharing.")
    elif covered < line_item.billed_amount:
        status = LineItemStatus.PARTIALLY_COVERED
        denial = None
        explanation_parts.append(
            f"Member responsibility: {line_item.billed_amount - covered - deductible_applied - copay_applied}."
        )
    else:
        status = LineItemStatus.COVERED
        denial = None

    explanation = " ".join(explanation_parts)

    adj = AdjudicationResult(
        id=result_id,
        line_item_id=line_item.id,
        covered_amount=covered,
        denial_reason=denial,
        explanation=explanation,
        adjudicated_at=now,
        deductible_applied=deductible_applied,
        copay_applied=copay_applied,
        applied_rule_id=rule.id,
    )
    line_item.adjudication = adj
    line_item.status = status

    return line_item, annual_usage


def _deny(
    line_item: LineItem,
    result_id: uuid.UUID,
    now: datetime,
    reason: DenialReason,
    explanation: str,
) -> LineItem:
    adj = AdjudicationResult(
        id=result_id,
        line_item_id=line_item.id,
        covered_amount=Money.zero(),
        denial_reason=reason,
        explanation=explanation,
        adjudicated_at=now,
        deductible_applied=Money.zero(),
        copay_applied=Money.zero(),
        applied_rule_id=None,
    )
    line_item.adjudication = adj
    line_item.status = LineItemStatus.DENIED
    return line_item
