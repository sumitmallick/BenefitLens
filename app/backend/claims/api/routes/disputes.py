"""
Dispute API routes.

Members dispute decisions; claims ops resolve them.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from claims.api.deps import get_current_user, require_roles
from claims.api.schemas import DisputeResponse, ResolveDisputeRequest, SubmitDisputeRequest
from claims.application.services import (
    ClaimNotFound,
    DisputeNotFound,
    SubmitDisputeCommand,
    resolve_dispute,
    submit_dispute,
)
from claims.domain.entities import Dispute
from claims.domain.state_machines import InvalidTransition
from claims.infrastructure.database import get_session
from claims.infrastructure.models import UserORM
from claims.infrastructure.repositories import DisputeRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/disputes", tags=["Disputes"])


def _dispute_response(d: Dispute) -> DisputeResponse:
    return DisputeResponse(
        id=d.id,
        claim_id=d.claim_id,
        line_item_id=d.line_item_id,
        reason=d.reason,
        status=d.status.value,
        submitted_at=d.submitted_at,
        resolved_at=d.resolved_at,
        resolution_notes=d.resolution_notes,
    )


@router.post(
    "/claims/{claim_id}",
    response_model=DisputeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a dispute for a claim or specific line item",
)
async def submit_dispute_endpoint(
    claim_id: uuid.UUID,
    request: SubmitDisputeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(get_current_user),
) -> DisputeResponse:
    cmd = SubmitDisputeCommand(
        claim_id=claim_id,
        reason=request.reason,
        line_item_id=request.line_item_id,
    )
    try:
        dispute = await submit_dispute(cmd, session)
    except ClaimNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Claim cannot be disputed in its current state: {exc}",
        )

    logger.info("Dispute submitted: dispute_id=%s claim_id=%s", dispute.id, claim_id)
    return _dispute_response(dispute)


@router.post(
    "/{dispute_id}/resolve",
    response_model=DisputeResponse,
    summary="Resolve a dispute (internal — claims ops team)",
)
async def resolve_dispute_endpoint(
    dispute_id: uuid.UUID,
    request: ResolveDisputeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
) -> DisputeResponse:
    try:
        dispute = await resolve_dispute(
            dispute_id=dispute_id,
            outcome=request.outcome,
            notes=request.notes,
            session=session,
        )
    except DisputeNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    logger.info("Dispute resolved: dispute_id=%s outcome=%s", dispute_id, request.outcome)
    return _dispute_response(dispute)


@router.get(
    "/claims/{claim_id}",
    summary="List disputes for a claim",
)
async def list_claim_disputes(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[DisputeResponse]:
    repo = DisputeRepository(session)
    disputes = await repo.list_by_claim(claim_id)
    return [_dispute_response(d) for d in disputes]
