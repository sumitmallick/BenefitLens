"""
Claims API routes.

All PHI access is logged at INFO level with claim_number and member_id only —
never the actual PHI values. Diagnosis codes are stripped from list endpoints.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from claims.api.schemas import (
    ClaimDetailResponse,
    ClaimResponse,
    ErrorResponse,
    LineItemDetailResponse,
    LineItemResponse,
    AdjudicationResultResponse,
    SubmitClaimRequest,
)
from claims.application.services import (
    ClaimNotFound,
    InvalidClaimState,
    MemberNotFound,
    PolicyNotFound,
    get_claim,
    list_claims_for_member,
    mark_claim_paid,
    submit_claim,
    SubmitClaimCommand,
)
from claims.api.deps import get_current_user, require_roles
from claims.infrastructure.repositories import ClaimRepository
from claims.infrastructure.models import UserORM
from claims.domain.entities import AdjudicationResult, Claim, LineItem
from claims.domain.state_machines import InvalidTransition
from claims.infrastructure.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["Claims"])


# ── Helpers ───────────────────────────────────────────────────────────────

def _adj_response(adj: AdjudicationResult | None) -> AdjudicationResultResponse | None:
    if adj is None:
        return None
    return AdjudicationResultResponse(
        covered_amount=adj.covered_amount.amount,
        denial_reason=adj.denial_reason.value if adj.denial_reason else None,
        explanation=adj.explanation,
        deductible_applied=adj.deductible_applied.amount,
        copay_applied=adj.copay_applied.amount,
        adjudicated_at=adj.adjudicated_at,
    )


def _line_item_response(li: LineItem) -> LineItemResponse:
    return LineItemResponse(
        id=li.id,
        service_type=li.service_type.value,
        service_date=li.service_date,
        billed_amount=li.billed_amount.amount,
        procedure_code=li.procedure_code,
        description=li.description,
        status=li.status.value,
        adjudication=_adj_response(li.adjudication),
    )


def _line_item_detail_response(li: LineItem) -> LineItemDetailResponse:
    return LineItemDetailResponse(
        id=li.id,
        service_type=li.service_type.value,
        service_date=li.service_date,
        billed_amount=li.billed_amount.amount,
        procedure_code=li.procedure_code,
        description=li.description,
        status=li.status.value,
        diagnosis_code=li.diagnosis_code,  # PHI — included only in detail endpoint
        adjudication=_adj_response(li.adjudication),
    )


def _claim_response(claim: Claim) -> ClaimResponse:
    return ClaimResponse(
        id=claim.id,
        claim_number=claim.claim_number,
        member_id=claim.member_id,
        policy_id=claim.policy_id,
        status=claim.status.value,
        submitted_at=claim.submitted_at,
        provider_name=claim.provider_name,
        provider_npi=claim.provider_npi,
        total_billed=claim.total_billed.amount,
        total_covered=claim.total_covered.amount,
        line_items=[_line_item_response(li) for li in claim.line_items],
    )


def _claim_detail_response(claim: Claim) -> ClaimDetailResponse:
    return ClaimDetailResponse(
        id=claim.id,
        claim_number=claim.claim_number,
        member_id=claim.member_id,
        policy_id=claim.policy_id,
        status=claim.status.value,
        submitted_at=claim.submitted_at,
        provider_name=claim.provider_name,
        provider_npi=claim.provider_npi,
        total_billed=claim.total_billed.amount,
        total_covered=claim.total_covered.amount,
        line_items=[_line_item_detail_response(li) for li in claim.line_items],
    )


# ── Routes ────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[ClaimResponse],
    summary="List claims — scope filtered by caller's role",
)
async def list_all_claims_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(get_current_user),
) -> List[ClaimResponse]:
    repo = ClaimRepository(session)

    if current_user.role in ("ADMIN", "CLAIM_PROCESSOR"):
        claims = await repo.list_all(limit=limit, offset=offset)
    elif current_user.role == "PATIENT":
        if not current_user.member_id:
            return []
        claims = await list_claims_for_member(current_user.member_id, session)
    elif current_user.role == "PROVIDER":
        if not current_user.provider_npi:
            return []
        claims = await repo.list_by_provider_npi(
            current_user.provider_npi, limit=limit, offset=offset
        )
    else:
        return []

    return [_claim_response(c) for c in claims]


@router.post(
    "/",
    response_model=ClaimDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new claim",
    description=(
        "Submit a claim with one or more line items. "
        "Adjudication runs synchronously and the response includes "
        "the adjudication result for each line item. "
        "Allowed roles: ADMIN, CLAIM_PROCESSOR, PROVIDER, PATIENT. "
        "PATIENT callers may only submit claims for their own member_id."
    ),
)
async def submit_claim_endpoint(
    request: SubmitClaimRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(get_current_user),
) -> ClaimDetailResponse:
    # PATIENT: can only submit for their own linked member
    if current_user.role == "PATIENT":
        if not current_user.member_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account does not have an insurance member record linked. "
                       "Visit /my-insurance to activate your insurance first.",
            )
        if request.member_id != current_user.member_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients may only submit claims for their own member record.",
            )
    elif current_user.role not in ("ADMIN", "CLAIM_PROCESSOR", "PROVIDER"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role}' is not authorized to submit claims.",
        )

    cmd = SubmitClaimCommand(
        member_id=request.member_id,
        policy_id=request.policy_id,
        provider_name=request.provider_name,
        provider_npi=request.provider_npi,
        line_items=[li.model_dump() for li in request.line_items],
    )
    try:
        claim = await submit_claim(cmd, session)
    except MemberNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PolicyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (ValueError, TypeError) as exc:
        logger.warning("Claim submission validation error: %s", exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    logger.info(
        "Claim submitted and adjudicated: claim_number=%s status=%s",
        claim.claim_number,
        claim.status.value,
    )
    return _claim_detail_response(claim)


@router.get(
    "/{claim_id}",
    response_model=ClaimDetailResponse,
    summary="Get claim detail with adjudication results",
)
async def get_claim_endpoint(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(get_current_user),
) -> ClaimDetailResponse:
    try:
        claim = await get_claim(claim_id, session)
    except ClaimNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    # Patients can only view their own claims
    if current_user.role == "PATIENT":
        if current_user.member_id != claim.member_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    # Providers can only view claims they submitted
    elif current_user.role == "PROVIDER":
        if current_user.provider_npi != claim.provider_npi:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    logger.info("Claim detail accessed: claim_number=%s", claim.claim_number)
    return _claim_detail_response(claim)


@router.get(
    "/member/{member_id}",
    response_model=List[ClaimResponse],
    summary="List all claims for a member (diagnosis codes excluded from list view)",
)
async def list_member_claims_endpoint(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> List[ClaimResponse]:
    claims = await list_claims_for_member(member_id, session)
    return [_claim_response(c) for c in claims]


@router.post(
    "/{claim_id}/pay",
    response_model=ClaimDetailResponse,
    summary="Mark an approved claim as paid (ADMIN / CLAIM_PROCESSOR only)",
)
async def mark_paid_endpoint(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
) -> ClaimDetailResponse:
    try:
        claim = await mark_claim_paid(claim_id, session)
    except ClaimNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return _claim_detail_response(claim)


@router.get(
    "/{claim_id}/explain",
    summary="Get human-readable explanation for every line item decision",
)
async def explain_claim_endpoint(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Returns structured explanations for each line item —
    the 'why' behind every coverage decision.
    """
    try:
        claim = await get_claim(claim_id, session)
    except ClaimNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    explanations = []
    for li in claim.line_items:
        adj = li.adjudication
        explanations.append({
            "line_item_id": str(li.id),
            "service_type": li.service_type.value,
            "service_date": li.service_date.isoformat(),
            "billed_amount": str(li.billed_amount.amount),
            "status": li.status.value,
            "covered_amount": str(adj.covered_amount.amount) if adj else "0.00",
            "denial_reason": adj.denial_reason.value if adj and adj.denial_reason else None,
            "explanation": adj.explanation if adj else "Not yet adjudicated.",
        })

    return {
        "claim_number": claim.claim_number,
        "claim_status": claim.status.value,
        "total_billed": str(claim.total_billed.amount),
        "total_covered": str(claim.total_covered.amount),
        "line_item_explanations": explanations,
    }
