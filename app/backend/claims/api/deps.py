"""
FastAPI security dependencies — JWT bearer authentication and RBAC enforcement.

Usage in routes:
    current_user: UserORM = Depends(get_current_user)               # any role
    admin: UserORM = Depends(require_roles("ADMIN"))                 # one role
    staff: UserORM = Depends(require_roles("ADMIN","CLAIM_PROCESSOR"))  # multiple
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claims.infrastructure.database import get_session
from claims.infrastructure.models import UserORM
from config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> UserORM:
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise auth_error
    except JWTError:
        raise auth_error

    result = await session.execute(
        select(UserORM).where(UserORM.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise auth_error
    return user


def require_roles(*roles: str):
    """
    Returns a FastAPI dependency that asserts the current user has one of the given roles.
    Raises 403 if the role does not match.
    """
    async def _guard(current_user: UserORM = Depends(get_current_user)) -> UserORM:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not authorized for this action",
            )
        return current_user
    return _guard
