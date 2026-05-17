"""
Value objects for the claims domain.
Immutable by convention; equality is structural, not identity-based.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ServiceType(str, Enum):
    """
    Canonical set of service types the adjudicator understands.
    Extending this enum is a deliberate change — not a config tweak.
    """
    PRIMARY_CARE = "PRIMARY_CARE"
    SPECIALIST_VISIT = "SPECIALIST_VISIT"
    EMERGENCY = "EMERGENCY"
    URGENT_CARE = "URGENT_CARE"
    PREVENTIVE = "PREVENTIVE"
    MENTAL_HEALTH = "MENTAL_HEALTH"
    PRESCRIPTION = "PRESCRIPTION"
    LAB_WORK = "LAB_WORK"
    IMAGING = "IMAGING"
    PHYSICAL_THERAPY = "PHYSICAL_THERAPY"
    INPATIENT = "INPATIENT"
    OUTPATIENT_SURGERY = "OUTPATIENT_SURGERY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    DURABLE_MEDICAL_EQUIPMENT = "DURABLE_MEDICAL_EQUIPMENT"


class ClaimStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    PARTIALLY_APPROVED = "PARTIALLY_APPROVED"
    DENIED = "DENIED"
    PAID = "PAID"
    DISPUTED = "DISPUTED"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED"
    VOIDED = "VOIDED"


class LineItemStatus(str, Enum):
    PENDING = "PENDING"
    COVERED = "COVERED"
    PARTIALLY_COVERED = "PARTIALLY_COVERED"
    DENIED = "DENIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DisputeStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    UPHELD = "UPHELD"   # member wins — decision reversed
    DENIED = "DENIED"   # original decision stands


class PolicyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class DenialReason(str, Enum):
    """
    Structured denial reasons — used both in the AdjudicationResult
    and surfaced verbatim to members in the explanation field.
    """
    NOT_COVERED_SERVICE = "NOT_COVERED_SERVICE"
    ANNUAL_LIMIT_EXHAUSTED = "ANNUAL_LIMIT_EXHAUSTED"
    PER_VISIT_LIMIT_EXCEEDED = "PER_VISIT_LIMIT_EXCEEDED"
    POLICY_INACTIVE = "POLICY_INACTIVE"
    SERVICE_DATE_OUT_OF_POLICY_PERIOD = "SERVICE_DATE_OUT_OF_POLICY_PERIOD"
    REQUIRES_PREAUTH = "REQUIRES_PREAUTH"
    EXCLUDED_DIAGNOSIS = "EXCLUDED_DIAGNOSIS"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    INCOMPLETE_INFORMATION = "INCOMPLETE_INFORMATION"


class NetworkType(str, Enum):
    IN_NETWORK = "IN_NETWORK"
    OUT_OF_NETWORK = "OUT_OF_NETWORK"
    ANY = "ANY"


@dataclass(frozen=True)
class Money:
    """
    All monetary values flow through Money to prevent raw float arithmetic.
    Uses Decimal internally; rounds to 2dp on construction.
    """
    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(self, "amount", self.amount.quantize(Decimal("0.01")))
        if self.amount < 0:
            raise ValueError(f"Money amount cannot be negative: {self.amount}")

    @classmethod
    def of(cls, value: float | int | str | Decimal) -> "Money":
        return cls(amount=Decimal(str(value)))

    @classmethod
    def zero(cls) -> "Money":
        return cls(amount=Decimal("0.00"))

    def __add__(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)

    def __sub__(self, other: "Money") -> "Money":
        if self.amount < other.amount:
            return Money.zero()
        return Money(self.amount - other.amount)

    def __mul__(self, factor: Decimal | float | int) -> "Money":
        return Money((self.amount * Decimal(str(factor))).quantize(Decimal("0.01")))

    def __le__(self, other: "Money") -> bool:
        return self.amount <= other.amount

    def __lt__(self, other: "Money") -> bool:
        return self.amount < other.amount

    def __ge__(self, other: "Money") -> bool:
        return self.amount >= other.amount

    def __gt__(self, other: "Money") -> bool:
        return self.amount > other.amount

    def __repr__(self) -> str:
        return f"${self.amount}"

    @property
    def is_zero(self) -> bool:
        return self.amount == Decimal("0.00")


@dataclass(frozen=True)
class DiagnosisCode:
    """ICD-10 code wrapper with basic format validation."""
    code: str

    def __post_init__(self) -> None:
        cleaned = self.code.strip().upper()
        object.__setattr__(self, "code", cleaned)
        if not re.match(r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$", cleaned):
            raise ValueError(f"Invalid ICD-10 diagnosis code format: {cleaned!r}")

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ProcedureCode:
    """CPT / HCPCS code wrapper."""
    code: str

    def __post_init__(self) -> None:
        cleaned = self.code.strip().upper()
        object.__setattr__(self, "code", cleaned)
        if not re.match(r"^[0-9]{5}([A-Z])?$|^[A-Z][0-9]{4}$", cleaned):
            raise ValueError(f"Invalid procedure code format: {cleaned!r}")

    def __str__(self) -> str:
        return self.code
