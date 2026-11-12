from datetime import datetime
from typing import Optional
import uuid

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.services.auth_service import verify_access_token

# OAuth2PasswordBearer extracts the token from the Authorization: Bearer header.
# auto_error=False means it returns None (not 401) when the header is absent,
# so we can fall back to checking the cookie.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve the current authenticated user from a JWT.

    Checks Authorization header first, then the access_token cookie.
    Raises HTTP 401 if no valid token is found.
    Raises HTTP 403 if the user's account is deactivated.
    """
    # Try header token first, then cookie
    raw_token = token or access_token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    verified = verify_access_token(raw_token)
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id, token_version = verified

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user and user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # A paid plan lapses when its period ends (PayPal orders are one-off, no
    # webhook cancels them). Downgrade lazily on the next authenticated request.
    if user.plan != "free" and user.plan_expires_at and user.plan_expires_at < datetime.utcnow():
        user.plan = "free"
        user.plan_expires_at = None
        await db.commit()

    return user


def require_plan(*plans: str):
    """
    Dependency factory that enforces a minimum subscription plan.

    Usage:
        @router.post("/cover-letter")
        async def cover_letter(user: User = Depends(require_plan("pro", "team"))):
            ...
    """
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.plan not in plans:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"This feature requires a {' or '.join(plans)} plan. "
                       f"You are on the '{user.plan}' plan.",
            )
        return user
    return _check


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Like get_current_user but returns None instead of raising 401.
    Use for endpoints that work both authenticated and unauthenticated.
    """
    raw_token = token or access_token
    if not raw_token:
        return None
    verified = verify_access_token(raw_token)
    if not verified:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(verified[0])))
    user = result.scalar_one_or_none()
    return user if user and user.token_version == verified[1] else None
