"""
State machine tests — written before the state machine implementation.

These tests encode the RULES, not the implementation.
They should read like a specification.
"""
import pytest

from claims.domain.state_machines import (
    CLAIM_TRANSITIONS,
    InvalidTransition,
    derive_claim_status_from_line_items,
    transition_claim,
    transition_dispute,
    transition_line_item,
)
from claims.domain.value_objects import ClaimStatus, DisputeStatus, LineItemStatus


# ── Claim state machine ───────────────────────────────────────────────────

class TestClaimTransitions:
    def test_submitted_can_move_to_under_review(self):
        result = transition_claim(ClaimStatus.SUBMITTED, ClaimStatus.UNDER_REVIEW)
        assert result == ClaimStatus.UNDER_REVIEW

    def test_submitted_can_be_voided(self):
        result = transition_claim(ClaimStatus.SUBMITTED, ClaimStatus.VOIDED)
        assert result == ClaimStatus.VOIDED

    def test_submitted_cannot_skip_to_approved(self):
        with pytest.raises(InvalidTransition) as exc_info:
            transition_claim(ClaimStatus.SUBMITTED, ClaimStatus.APPROVED)
        assert "SUBMITTED" in str(exc_info.value)
        assert "APPROVED" in str(exc_info.value)

    def test_under_review_can_approve(self):
        assert transition_claim(ClaimStatus.UNDER_REVIEW, ClaimStatus.APPROVED) == ClaimStatus.APPROVED

    def test_under_review_can_partially_approve(self):
        assert (
            transition_claim(ClaimStatus.UNDER_REVIEW, ClaimStatus.PARTIALLY_APPROVED)
            == ClaimStatus.PARTIALLY_APPROVED
        )

    def test_under_review_can_deny(self):
        assert transition_claim(ClaimStatus.UNDER_REVIEW, ClaimStatus.DENIED) == ClaimStatus.DENIED

    def test_approved_can_move_to_paid(self):
        assert transition_claim(ClaimStatus.APPROVED, ClaimStatus.PAID) == ClaimStatus.PAID

    def test_approved_can_be_disputed(self):
        assert transition_claim(ClaimStatus.APPROVED, ClaimStatus.DISPUTED) == ClaimStatus.DISPUTED

    def test_denied_can_be_disputed(self):
        assert transition_claim(ClaimStatus.DENIED, ClaimStatus.DISPUTED) == ClaimStatus.DISPUTED

    def test_paid_is_terminal(self):
        with pytest.raises(InvalidTransition):
            transition_claim(ClaimStatus.PAID, ClaimStatus.APPROVED)

    def test_voided_is_terminal(self):
        with pytest.raises(InvalidTransition):
            transition_claim(ClaimStatus.VOIDED, ClaimStatus.SUBMITTED)

    def test_disputed_resolves_to_dispute_resolved(self):
        assert (
            transition_claim(ClaimStatus.DISPUTED, ClaimStatus.DISPUTE_RESOLVED)
            == ClaimStatus.DISPUTE_RESOLVED
        )

    def test_dispute_resolved_can_move_to_paid(self):
        assert (
            transition_claim(ClaimStatus.DISPUTE_RESOLVED, ClaimStatus.PAID)
            == ClaimStatus.PAID
        )


# ── LineItem state machine ────────────────────────────────────────────────

class TestLineItemTransitions:
    def test_pending_to_covered(self):
        assert transition_line_item(LineItemStatus.PENDING, LineItemStatus.COVERED) == LineItemStatus.COVERED

    def test_pending_to_denied(self):
        assert transition_line_item(LineItemStatus.PENDING, LineItemStatus.DENIED) == LineItemStatus.DENIED

    def test_pending_to_partially_covered(self):
        assert (
            transition_line_item(LineItemStatus.PENDING, LineItemStatus.PARTIALLY_COVERED)
            == LineItemStatus.PARTIALLY_COVERED
        )

    def test_pending_to_needs_review(self):
        assert (
            transition_line_item(LineItemStatus.PENDING, LineItemStatus.NEEDS_REVIEW)
            == LineItemStatus.NEEDS_REVIEW
        )

    def test_needs_review_can_resolve_to_covered(self):
        assert (
            transition_line_item(LineItemStatus.NEEDS_REVIEW, LineItemStatus.COVERED)
            == LineItemStatus.COVERED
        )

    def test_covered_is_terminal(self):
        with pytest.raises(InvalidTransition):
            transition_line_item(LineItemStatus.COVERED, LineItemStatus.PENDING)

    def test_denied_is_terminal(self):
        with pytest.raises(InvalidTransition):
            transition_line_item(LineItemStatus.DENIED, LineItemStatus.COVERED)


# ── Dispute state machine ─────────────────────────────────────────────────

class TestDisputeTransitions:
    def test_submitted_to_under_review(self):
        assert (
            transition_dispute(DisputeStatus.SUBMITTED, DisputeStatus.UNDER_REVIEW)
            == DisputeStatus.UNDER_REVIEW
        )

    def test_under_review_upheld(self):
        assert (
            transition_dispute(DisputeStatus.UNDER_REVIEW, DisputeStatus.UPHELD)
            == DisputeStatus.UPHELD
        )

    def test_under_review_denied(self):
        assert (
            transition_dispute(DisputeStatus.UNDER_REVIEW, DisputeStatus.DENIED)
            == DisputeStatus.DENIED
        )

    def test_upheld_is_terminal(self):
        with pytest.raises(InvalidTransition):
            transition_dispute(DisputeStatus.UPHELD, DisputeStatus.SUBMITTED)


# ── derive_claim_status_from_line_items ───────────────────────────────────

class TestDeriveClaimStatus:
    def test_all_covered_yields_approved(self):
        statuses = [LineItemStatus.COVERED, LineItemStatus.COVERED]
        assert derive_claim_status_from_line_items(statuses) == ClaimStatus.APPROVED

    def test_all_denied_yields_denied(self):
        statuses = [LineItemStatus.DENIED, LineItemStatus.DENIED]
        assert derive_claim_status_from_line_items(statuses) == ClaimStatus.DENIED

    def test_mixed_yields_partially_approved(self):
        statuses = [LineItemStatus.COVERED, LineItemStatus.DENIED]
        assert derive_claim_status_from_line_items(statuses) == ClaimStatus.PARTIALLY_APPROVED

    def test_any_needs_review_yields_under_review(self):
        statuses = [LineItemStatus.COVERED, LineItemStatus.NEEDS_REVIEW]
        assert derive_claim_status_from_line_items(statuses) == ClaimStatus.UNDER_REVIEW

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            derive_claim_status_from_line_items([])

    def test_partially_covered_mixed_with_denied_yields_partially_approved(self):
        statuses = [LineItemStatus.PARTIALLY_COVERED, LineItemStatus.DENIED]
        assert derive_claim_status_from_line_items(statuses) == ClaimStatus.PARTIALLY_APPROVED
