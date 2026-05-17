"""
Domain event types published after claim state changes.

These events flow via an internal in-process bus during tests,
and via Kafka (or SQS in AWS) in production — the infrastructure
layer adapts them; the domain only defines the shape.

Event naming convention: <Aggregate><PastTenseVerb>
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .value_objects import ClaimStatus, DenialReason, LineItemStatus, ServiceType


@dataclass(frozen=True)
class ClaimSubmitted:
    event_id: uuid.UUID
    claim_id: uuid.UUID
    claim_number: str
    member_id: uuid.UUID
    policy_id: uuid.UUID
    submitted_at: datetime
    line_item_count: int
    total_billed_cents: int   # stored as int cents to avoid float in events


@dataclass(frozen=True)
class ClaimStatusChanged:
    event_id: uuid.UUID
    claim_id: uuid.UUID
    claim_number: str
    from_status: ClaimStatus
    to_status: ClaimStatus
    changed_at: datetime
    actor: str = "system"


@dataclass(frozen=True)
class LineItemAdjudicated:
    event_id: uuid.UUID
    claim_id: uuid.UUID
    line_item_id: uuid.UUID
    service_type: ServiceType
    billed_cents: int
    covered_cents: int
    status: LineItemStatus
    denial_reason: Optional[DenialReason]
    adjudicated_at: datetime


@dataclass(frozen=True)
class DisputeSubmitted:
    event_id: uuid.UUID
    dispute_id: uuid.UUID
    claim_id: uuid.UUID
    line_item_id: Optional[uuid.UUID]
    submitted_at: datetime


@dataclass(frozen=True)
class DisputeResolved:
    event_id: uuid.UUID
    dispute_id: uuid.UUID
    claim_id: uuid.UUID
    outcome: str        # "UPHELD" | "DENIED"
    resolved_at: datetime
