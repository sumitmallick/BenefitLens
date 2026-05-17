"""
Explicit state machines for Claim and LineItem lifecycles.

Design choice: transitions are data (dict), not method dispatch.
This makes them inspectable/testable without triggering side effects,
and lets us serialize the valid transitions to an audit log.

The state machine does NOT own persistence — it returns the next state
or raises InvalidTransition. The application service writes to the DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Set

from .value_objects import ClaimStatus, DisputeStatus, LineItemStatus


class InvalidTransition(Exception):
    def __init__(self, entity: str, from_state: str, to_state: str) -> None:
        self.entity = entity
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"{entity} cannot transition {from_state!r} → {to_state!r}"
        )


# ---------------------------------------------------------------------------
# Claim state machine
# ---------------------------------------------------------------------------

CLAIM_TRANSITIONS: Dict[ClaimStatus, FrozenSet[ClaimStatus]] = {
    ClaimStatus.SUBMITTED: frozenset({ClaimStatus.UNDER_REVIEW, ClaimStatus.VOIDED}),
    ClaimStatus.UNDER_REVIEW: frozenset({
        ClaimStatus.APPROVED,
        ClaimStatus.PARTIALLY_APPROVED,
        ClaimStatus.DENIED,
        ClaimStatus.VOIDED,
    }),
    ClaimStatus.APPROVED: frozenset({ClaimStatus.PAID, ClaimStatus.DISPUTED}),
    ClaimStatus.PARTIALLY_APPROVED: frozenset({ClaimStatus.PAID, ClaimStatus.DISPUTED}),
    ClaimStatus.DENIED: frozenset({ClaimStatus.DISPUTED}),
    ClaimStatus.PAID: frozenset(),          # terminal
    ClaimStatus.DISPUTED: frozenset({ClaimStatus.DISPUTE_RESOLVED}),
    ClaimStatus.DISPUTE_RESOLVED: frozenset({ClaimStatus.PAID}),
    ClaimStatus.VOIDED: frozenset(),        # terminal
}

TERMINAL_CLAIM_STATUSES: Set[ClaimStatus] = {
    ClaimStatus.PAID,
    ClaimStatus.VOIDED,
}


def transition_claim(current: ClaimStatus, target: ClaimStatus) -> ClaimStatus:
    """Return target if the transition is valid; raise otherwise."""
    allowed = CLAIM_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransition("Claim", current.value, target.value)
    return target


# ---------------------------------------------------------------------------
# LineItem state machine
# ---------------------------------------------------------------------------

LINE_ITEM_TRANSITIONS: Dict[LineItemStatus, FrozenSet[LineItemStatus]] = {
    LineItemStatus.PENDING: frozenset({
        LineItemStatus.COVERED,
        LineItemStatus.PARTIALLY_COVERED,
        LineItemStatus.DENIED,
        LineItemStatus.NEEDS_REVIEW,
    }),
    LineItemStatus.NEEDS_REVIEW: frozenset({
        LineItemStatus.COVERED,
        LineItemStatus.PARTIALLY_COVERED,
        LineItemStatus.DENIED,
    }),
    LineItemStatus.COVERED: frozenset(),        # terminal after adjudication
    LineItemStatus.PARTIALLY_COVERED: frozenset(),
    LineItemStatus.DENIED: frozenset(),
}

TERMINAL_LINE_ITEM_STATUSES: Set[LineItemStatus] = {
    LineItemStatus.COVERED,
    LineItemStatus.PARTIALLY_COVERED,
    LineItemStatus.DENIED,
}


def transition_line_item(current: LineItemStatus, target: LineItemStatus) -> LineItemStatus:
    allowed = LINE_ITEM_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransition("LineItem", current.value, target.value)
    return target


# ---------------------------------------------------------------------------
# Dispute state machine
# ---------------------------------------------------------------------------

DISPUTE_TRANSITIONS: Dict[DisputeStatus, FrozenSet[DisputeStatus]] = {
    DisputeStatus.SUBMITTED: frozenset({DisputeStatus.UNDER_REVIEW}),
    DisputeStatus.UNDER_REVIEW: frozenset({DisputeStatus.UPHELD, DisputeStatus.DENIED}),
    DisputeStatus.UPHELD: frozenset(),   # terminal
    DisputeStatus.DENIED: frozenset(),   # terminal
}


def transition_dispute(current: DisputeStatus, target: DisputeStatus) -> DisputeStatus:
    allowed = DISPUTE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransition("Dispute", current.value, target.value)
    return target


# ---------------------------------------------------------------------------
# Helpers for computing aggregate claim status from line item outcomes
# ---------------------------------------------------------------------------

def derive_claim_status_from_line_items(statuses: list[LineItemStatus]) -> ClaimStatus:
    """
    After adjudication, determine the appropriate claim status based on
    the collection of line-item outcomes.

    Rules (in priority order):
    1. Any NEEDS_REVIEW → keep UNDER_REVIEW (adjudication not complete)
    2. All DENIED         → DENIED
    3. All COVERED        → APPROVED
    4. Mixed              → PARTIALLY_APPROVED
    """
    if not statuses:
        raise ValueError("Cannot derive claim status from empty line items")

    if any(s == LineItemStatus.NEEDS_REVIEW for s in statuses):
        return ClaimStatus.UNDER_REVIEW

    unique = set(statuses)

    if unique == {LineItemStatus.DENIED}:
        return ClaimStatus.DENIED

    if unique == {LineItemStatus.COVERED}:
        return ClaimStatus.APPROVED

    # Mix of covered/partially_covered/denied
    return ClaimStatus.PARTIALLY_APPROVED
