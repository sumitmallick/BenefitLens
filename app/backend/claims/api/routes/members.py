"""
Member & Policy management routes.

Scoped to what's needed to demo the system — not a full member portal.
Out of scope per assignment: registration, auth, account management.
"""
from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from claims.api.schemas import (
    CreateMemberRequest,
    CreatePolicyRequest,
    MemberResponse,
    PolicyResponse,
)
from claims.application.services import create_member, create_policy
from claims.infrastructure.database import get_session
from claims.infrastructure.repositories import MemberRepository, PolicyRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Members & Policies"])


@router.post(
    "/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a member (for demo/testing)",
)
async def create_member_endpoint(
    request: CreateMemberRequest,
    session: AsyncSession = Depends(get_session),
) -> MemberResponse:
    member = await create_member(
        member_id_str=request.member_id,
        name=request.name,
        date_of_birth=request.date_of_birth,
        email=request.email,
        session=session,
    )
    # Minimal PHI in response — name only, no DOB/email
    return MemberResponse(id=member.id, member_id=member.member_id, name=member.name)


@router.get(
    "/members/{member_id}",
    response_model=MemberResponse,
    summary="Get member by ID",
)
async def get_member_endpoint(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MemberResponse:
    repo = MemberRepository(session)
    member = await repo.get(member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return MemberResponse(id=member.id, member_id=member.member_id, name=member.name)


@router.post(
    "/policies",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a policy with coverage rules (for demo/testing)",
)
async def create_policy_endpoint(
    request: CreatePolicyRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyResponse:
    policy = await create_policy(
        member_id=request.member_id,
        policy_number=request.policy_number,
        effective_date=request.effective_date,
        expiration_date=request.expiration_date,
        deductible_amount=str(request.deductible_amount),
        out_of_pocket_max=str(request.out_of_pocket_max),
        coverage_rules=[r.model_dump() for r in request.coverage_rules],
        session=session,
    )
    return PolicyResponse(
        id=policy.id,
        member_id=policy.member_id,
        policy_number=policy.policy_number,
        effective_date=policy.effective_date,
        expiration_date=policy.expiration_date,
        status=policy.status.value,
        deductible_amount=policy.deductible_amount.amount,
        deductible_met=policy.deductible_met.amount,
        out_of_pocket_max=policy.out_of_pocket_max.amount if policy.out_of_pocket_max else None,
        coverage_rules=[
            {
                "service_type": r.service_type.value,
                "coverage_percentage": str(r.coverage_percentage),
                "annual_limit": str(r.annual_limit.amount) if r.annual_limit else None,
                "per_visit_limit": str(r.per_visit_limit.amount) if r.per_visit_limit else None,
                "copay": str(r.copay.amount) if r.copay else None,
                "requires_preauth": r.requires_preauth,
            }
            for r in policy.coverage_rules
        ],
    )


@router.get(
    "/policies/{policy_id}",
    response_model=PolicyResponse,
    summary="Get policy details",
)
async def get_policy_endpoint(
    policy_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PolicyResponse:
    repo = PolicyRepository(session)
    policy = await repo.get(policy_id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return PolicyResponse(
        id=policy.id,
        member_id=policy.member_id,
        policy_number=policy.policy_number,
        effective_date=policy.effective_date,
        expiration_date=policy.expiration_date,
        status=policy.status.value,
        deductible_amount=policy.deductible_amount.amount,
        deductible_met=policy.deductible_met.amount,
        out_of_pocket_max=policy.out_of_pocket_max.amount if policy.out_of_pocket_max else None,
        coverage_rules=[
            {
                "service_type": r.service_type.value,
                "coverage_percentage": str(r.coverage_percentage),
                "annual_limit": str(r.annual_limit.amount) if r.annual_limit else None,
                "per_visit_limit": str(r.per_visit_limit.amount) if r.per_visit_limit else None,
                "copay": str(r.copay.amount) if r.copay else None,
                "requires_preauth": r.requires_preauth,
            }
            for r in policy.coverage_rules
        ],
    )
