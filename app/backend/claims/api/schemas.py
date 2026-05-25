"""
Pydantic v2 schemas for the API layer.

Separation of concerns: API schemas != domain entities.
This lets us version the API independently of the domain model,
and carefully control what PHI fields are exposed in responses
(e.g., diagnosis codes are never returned in list views).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Request schemas ───────────────────────────────────────────────────────

class LineItemRequest(BaseModel):
    service_type: str = Field(..., description="ServiceType enum value")
    service_date: date
    billed_amount: Decimal = Field(..., gt=0, description="Amount billed by provider (USD)")
    diagnosis_code: str = Field(..., description="ICD-10 diagnosis code (PHI)")
    procedure_code: str = Field(..., description="CPT/HCPCS procedure code")
    description: str = Field(default="", max_length=512)

    @field_validator("billed_amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("billed_amount must be positive")
        return v


class SubmitClaimRequest(BaseModel):
    member_id: uuid.UUID
    policy_id: uuid.UUID
    provider_name: str = Field(..., min_length=1, max_length=256)
    provider_npi: str = Field(..., min_length=10, max_length=10, description="10-digit NPI")
    line_items: List[LineItemRequest] = Field(..., min_length=1)

    @field_validator("provider_npi")
    @classmethod
    def npi_must_be_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("provider_npi must be 10 digits")
        return v


class SubmitDisputeRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000, description="Member's grounds for dispute")
    line_item_id: Optional[uuid.UUID] = Field(
        None,
        description="Specific line item to dispute; omit to dispute the entire claim",
    )


class ResolveDisputeRequest(BaseModel):
    outcome: str = Field(..., description="'UPHELD' or 'DENIED'")
    notes: str = Field(..., min_length=5, max_length=2000)

    @field_validator("outcome")
    @classmethod
    def outcome_must_be_valid(cls, v: str) -> str:
        if v not in ("UPHELD", "DENIED"):
            raise ValueError("outcome must be 'UPHELD' or 'DENIED'")
        return v


class CreateMemberRequest(BaseModel):
    member_id: str = Field(..., description="Plan-issued member ID (PHI)")
    name: str = Field(..., min_length=1, max_length=256, description="Full name (PHI)")
    date_of_birth: date = Field(..., description="Date of birth (PHI)")
    email: str = Field(..., description="Contact email (PHI)")


class CoverageRuleRequest(BaseModel):
    service_type: str
    coverage_percentage: Decimal = Field(..., ge=0, le=100)
    annual_limit: Optional[Decimal] = Field(None, gt=0)
    per_visit_limit: Optional[Decimal] = Field(None, gt=0)
    copay: Optional[Decimal] = Field(None, ge=0)
    requires_preauth: bool = False
    network_restriction: str = "ANY"
    excluded_diagnosis_codes: List[str] = Field(default_factory=list)


class CreatePolicyRequest(BaseModel):
    holder_member_id: uuid.UUID = Field(..., description="Primary subscriber — the member who holds the contract")
    policy_number: str = Field(..., min_length=1, max_length=64)
    effective_date: date
    expiration_date: date
    deductible_amount: Decimal = Field(..., ge=0)
    out_of_pocket_max: Decimal = Field(..., gt=0)
    coverage_rules: List[CoverageRuleRequest] = Field(..., min_length=1)


class AddMemberToPolicyRequest(BaseModel):
    member_id: uuid.UUID = Field(..., description="Member to enroll as a dependent")
    relationship: str = Field(
        ...,
        description="Relationship to the policy holder: SPOUSE | CHILD | OTHER_DEPENDENT",
    )
    enrollment_date: date = Field(..., description="Date coverage begins for this member")


# ── Response schemas ──────────────────────────────────────────────────────

class AdjudicationResultResponse(BaseModel):
    covered_amount: Decimal
    denial_reason: Optional[str]
    explanation: str
    deductible_applied: Decimal
    copay_applied: Decimal
    adjudicated_at: datetime


class LineItemResponse(BaseModel):
    id: uuid.UUID
    service_type: str
    service_date: date
    billed_amount: Decimal
    procedure_code: str
    description: str
    status: str
    # diagnosis_code intentionally omitted from list responses — returned only in detail
    adjudication: Optional[AdjudicationResultResponse] = None


class LineItemDetailResponse(LineItemResponse):
    """Full line item with PHI diagnosis code — only returned in claim detail view."""
    diagnosis_code: str   # PHI — requires appropriate access control in production


class ClaimResponse(BaseModel):
    id: uuid.UUID
    claim_number: str
    member_id: uuid.UUID
    policy_id: uuid.UUID
    status: str
    submitted_at: datetime
    provider_name: str
    provider_npi: str
    total_billed: Decimal
    total_covered: Decimal
    line_items: List[LineItemResponse]


class ClaimDetailResponse(ClaimResponse):
    line_items: List[LineItemDetailResponse]


class DisputeResponse(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    line_item_id: Optional[uuid.UUID]
    reason: str
    status: str
    submitted_at: datetime
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]


class MemberResponse(BaseModel):
    id: uuid.UUID
    member_id: str
    name: str
    # date_of_birth and email omitted from response — minimal PHI exposure


class PolicyResponse(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    policy_number: str
    effective_date: date
    expiration_date: date
    status: str
    deductible_amount: Decimal
    deductible_met: Decimal
    out_of_pocket_max: Optional[Decimal]
    coverage_rules: List[dict]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
