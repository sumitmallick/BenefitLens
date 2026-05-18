"""
Authentication routes — register, login, profile management.

POST /api/v1/auth/register   — create account (any role)
POST /api/v1/auth/login      — OAuth2 password flow → JWT
GET  /api/v1/auth/me         — current user profile
GET  /api/v1/auth/users      — list all users (ADMIN only)
PATCH /api/v1/auth/users/{id}/role — change user role (ADMIN only)
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claims.api.deps import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from claims.api.rate_limit import limiter
from claims.infrastructure.database import get_session
from claims.infrastructure.models import UserORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

VALID_ROLES = {"ADMIN", "CLAIM_PROCESSOR", "PATIENT", "PROVIDER"}


# ── Request / Response schemas ────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "PATIENT"
    # PATIENT: optionally link to existing member record
    member_id: Optional[str] = None
    # PROVIDER: NPI + organization name
    provider_npi: Optional[str] = None
    provider_name: Optional[str] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("provider_npi")
    @classmethod
    def validate_npi(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit() or (v is not None and len(v) != 10):
            raise ValueError("Provider NPI must be exactly 10 digits")
        return v


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    member_id: Optional[str] = None
    provider_npi: Optional[str] = None
    provider_name: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UpdateRoleRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────

def _user_response(user: UserORM) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        member_id=str(user.member_id) if user.member_id else None,
        provider_npi=user.provider_npi,
        provider_name=user.provider_name,
        is_active=user.is_active,
    )


# ── Routes ────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    existing = await session.scalar(
        select(UserORM).where(UserORM.email == payload.email.lower().strip())
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists",
        )

    user = UserORM(
        id=uuid.uuid4(),
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        member_id=uuid.UUID(payload.member_id) if payload.member_id else None,
        provider_npi=payload.provider_npi,
        provider_name=payload.provider_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info("New user registered: role=%s", user.role)
    token = create_access_token(str(user.id), user.role)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain a JWT access token",
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await session.scalar(
        select(UserORM).where(UserORM.email == form_data.username.lower().strip())
    )
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    logger.info("User logged in: role=%s", user.role)
    token = create_access_token(str(user.id), user.role)
    return TokenResponse(access_token=token, user=_user_response(user))


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(current_user: UserORM = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List all platform users (ADMIN only)",
)
async def list_users(
    current_user: UserORM = Depends(require_roles("ADMIN")),
    session: AsyncSession = Depends(get_session),
) -> List[UserResponse]:
    result = await session.execute(select(UserORM).order_by(UserORM.created_at.desc()))
    users = result.scalars().all()
    return [_user_response(u) for u in users]


@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
    summary="Update a user's role (ADMIN only)",
)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UpdateRoleRequest,
    current_user: UserORM = Depends(require_roles("ADMIN")),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    user = await session.scalar(select(UserORM).where(UserORM.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = payload.role
    await session.commit()
    await session.refresh(user)
    logger.info("User role updated: user_id=%s new_role=%s by_admin=%s", user_id, payload.role, current_user.id)
    return _user_response(user)


@router.patch(
    "/users/{user_id}/deactivate",
    response_model=UserResponse,
    summary="Deactivate a user account (ADMIN only)",
)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: UserORM = Depends(require_roles("ADMIN")),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    user = await session.scalar(select(UserORM).where(UserORM.id == user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = False
    await session.commit()
    await session.refresh(user)
    return _user_response(user)
