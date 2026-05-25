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
    AddMemberToPolicyRequest,
    CreateMemberRequest,
    CreatePolicyRequest,
    MemberResponse,
    MembershipPolicyResponse,
    PolicyResponse,
)
from claims.api.deps import get_current_user, require_roles
from claims.application.services import (
    MemberAlreadyEnrolled,
    MemberNotFound,
    MembershipNotFound,
    PolicyNotFound,
    add_member_to_policy,
    create_member,
    create_policy,
    remove_member_from_policy,
)
from claims.infrastructure.database import get_session
from claims.infrastructure.models import UserORM
from claims.infrastructure.repositories import MemberRepository, MembershipPolicyRepository, PolicyRepository

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
            holder_member_id=policy.holder_member_id,
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
        holder_member_id=request.holder_member_id,
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
        holder_member_id=policy.holder_member_id,
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
        holder_member_id=policy.holder_member_id,
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


# ── Membership management endpoints ───────────────────────────────────────────


def _membership_resp(m) -> MembershipPolicyResponse:
    return MembershipPolicyResponse(
        id=m.id,
        policy_id=m.policy_id,
        member_id=m.member_id,
        relationship=m.relationship,
        enrollment_date=m.enrollment_date,
        termination_date=m.termination_date,
        status=m.status,
        coverage_rules=[
            {
                "service_type": r.service_type.value,
                "coverage_percentage": str(r.coverage_percentage),
                "annual_limit": str(r.annual_limit.amount) if r.annual_limit else None,
                "per_visit_limit": str(r.per_visit_limit.amount) if r.per_visit_limit else None,
                "copay": str(r.copay.amount) if r.copay else None,
                "requires_preauth": r.requires_preauth,
            }
            for r in m.coverage_rules
        ],
    )


@router.get(
    "/policies/{policy_id}/members",
    response_model=List[MembershipPolicyResponse],
    summary="List all members enrolled in a policy (ADMIN / CLAIM_PROCESSOR only)",
)
async def list_policy_members_endpoint(
    policy_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
) -> List[MembershipPolicyResponse]:
    repo = MembershipPolicyRepository(session)
    memberships = await repo.list_by_policy(policy_id)
    return [_membership_resp(m) for m in memberships]


@router.post(
    "/policies/{policy_id}/members",
    response_model=MembershipPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Enroll a dependent under a policy (ADMIN / CLAIM_PROCESSOR only). "
        "Optionally supply per-member coverage_rules to override policy defaults for this member."
    ),
)
async def add_member_to_policy_endpoint(
    policy_id: uuid.UUID,
    request: AddMemberToPolicyRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
) -> MembershipPolicyResponse:
    try:
        membership = await add_member_to_policy(
            policy_id=policy_id,
            member_id=request.member_id,
            relationship=request.relationship,
            enrollment_date=request.enrollment_date,
            coverage_rules=[r.model_dump() for r in request.coverage_rules] if request.coverage_rules else None,
            session=session,
        )
    except PolicyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except MemberNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except MemberAlreadyEnrolled as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return _membership_resp(membership)


@router.delete(
    "/policies/{policy_id}/members/{member_id}",
    response_model=MembershipPolicyResponse,
    summary="Terminate a dependent's enrollment under a policy (ADMIN / CLAIM_PROCESSOR only)",
)
async def remove_member_from_policy_endpoint(
    policy_id: uuid.UUID,
    member_id: uuid.UUID,
    termination_date: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    current_user: UserORM = Depends(require_roles("ADMIN", "CLAIM_PROCESSOR")),
) -> MembershipPolicyResponse:
    from datetime import date as date_type
    term_date = (
        date_type.fromisoformat(termination_date)
        if termination_date
        else date_type.today()
    )
    try:
        membership = await remove_member_from_policy(
            policy_id=policy_id,
            member_id=member_id,
            termination_date=term_date,
            session=session,
        )
    except MembershipNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _membership_resp(membership)
