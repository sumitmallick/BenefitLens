"""
Member & Policy management routes.

Production CRUD endpoints for the claims processing platform.
PHI fields (name, DOB, email) are encrypted at rest; responses return
the minimum necessary PHI subset consistent with the access level.
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from claims.api.schemas import (
    CreateMemberRequest,
    CreatePolicyRequest,
    MemberResponse,
    PolicyResponse,
)
from claims.api.deps import get_current_user, require_roles
from claims.application.services import create_member, create_policy
from claims.infrastructure.database import get_session
from claims.infrastructure.models import UserORM
from claims.infrastructure.repositories import MemberRepository, PolicyRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Members & Policies"])


@router.get(
    "/members",
    response_model=List[MemberResponse],
    summary="List members — scope filtered by caller's role",
)
async def list_members_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(get_current_user),
) -> List[MemberResponse]:
    repo = MemberRepository(session)

    if current_user.role in ("ADMIN", "CLAIM_PROCESSOR", "PROVIDER"):
        members = await repo.list_all(limit=limit, offset=offset)
    elif current_user.role == "PATIENT":
        # Patients see only their linked member record
        if not current_user.member_id:
            return []
        member = await repo.get(current_user.member_id)
        members = [member] if member else []
    else:
        return []

    return [MemberResponse(id=m.id, member_id=m.member_id, name=m.name) for m in members]


@router.get(
    "/policies",
    response_model=List[PolicyResponse],
    summary="List all policies (paginated)",
)
async def list_policies_endpoint(
    member_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> List[PolicyResponse]:
    repo = PolicyRepository(session)
    if member_id:
        policies = await repo.get_by_member(member_id)
    else:
        policies = await repo.list_all(limit=limit, offset=offset)

    def _policy_resp(policy) -> PolicyResponse:
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

    return [_policy_resp(p) for p in policies]


@router.post(
    "/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new member (ADMIN / CLAIM_PROCESSOR only)",
)
async def create_member_endpoint(
    request: CreateMemberRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
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
    current_user: UserORM = Depends(get_current_user),
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
    summary="Create a policy with coverage rules (ADMIN / CLAIM_PROCESSOR only)",
)
async def create_policy_endpoint(
    request: CreatePolicyRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
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
