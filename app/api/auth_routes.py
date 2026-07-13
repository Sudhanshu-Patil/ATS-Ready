from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services.auth_service import (
    create_access_token,
    create_email_verify_token,
    create_refresh_token,
    create_reset_token,
    decode_token,
    hash_password,
    verify_access_token,
    verify_email_verify_token,
    verify_password,
    verify_refresh_token,
    verify_reset_token,
)
from app.services.email_service import send_password_reset_email, send_verification_email
from app.config import settings

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    plan: str


# ── Cookie helper ─────────────────────────────────────────────────────────────

def _set_auth_cookies(response: Response, user_id: int) -> str:
    """Set httpOnly auth cookies and return the access token string."""
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    cookie_kwargs = dict(
        httponly=True,
        samesite="lax",
        secure=settings.is_production,  # HTTPS-only in prod
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 86_400,
        **cookie_kwargs,
    )
    return access_token


# ── Endpoints ─────────────────────────────────────────────────────────────────

@auth_router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    data: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new account with email + password.
    Returns tokens immediately — no email verification required in dev.
    (Add email verification in production before launch.)
    """
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        is_active=True,
        is_verified=False,   # set True after email verification
        plan="free",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = _set_auth_cookies(response, user.id)

    # Best-effort verification email — registration must succeed even when
    # SMTP is down/unconfigured (send_email never raises).
    await send_verification_email(user.email, create_email_verify_token(user.id))

    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name or "",
        plan=user.plan,
    )


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email + password.
    Uses OAuth2PasswordRequestForm so it works with the Swagger UI
    "Authorize" button and standard OAuth2 clients.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = _set_auth_cookies(response, user.id)

    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name or "",
        plan=user.plan,
    )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access token.
    The refresh token must be in the httpOnly cookie.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token found",
        )

    user_id = verify_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired. Please log in again.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    access_token = _set_auth_cookies(response, user.id)

    return TokenResponse(
        access_token=access_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name or "",
        plan=user.plan,
    )


@auth_router.post("/logout")
async def logout(response: Response):
    """Clear auth cookies. The tokens are not blocklisted (stateless JWT)."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}


@auth_router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return {
        "id":         str(user.id),
        "email":      user.email,
        "full_name":  user.full_name,
        "plan":       user.plan,
        "is_verified": user.is_verified,
        "created_at": str(user.created_at),
    }


@auth_router.patch("/me")
async def update_me(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's full_name."""
    allowed = {"full_name"}
    for key, value in data.items():
        if key in allowed:
            setattr(user, key, value)
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Profile updated"}


@auth_router.post("/change-password")
async def change_password(
    data: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password — requires current password for verification."""
    current = data.get("current_password", "")
    new = data.get("new_password", "")

    if not user.hashed_password or not verify_password(current, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(new) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user.hashed_password = hash_password(new)
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Password changed successfully"}


# ── Password reset (forgot password) ──────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@auth_router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a password-reset link if the account exists.

    ALWAYS returns the same 200 response — revealing whether an email is
    registered would let attackers enumerate accounts.
    """
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        token = create_reset_token(user.id, user.hashed_password)
        await send_password_reset_email(user.email, token)

    return {"message": "If that email is registered, a reset link has been sent."}


@auth_router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Set a new password using a reset token from the email link.

    Tokens are single-use: they embed a fingerprint of the password hash
    they were issued against, so completing a reset invalidates the token.
    """
    payload = decode_token(data.token)
    if not payload or payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired")

    result = await db.execute(select(User).where(User.id == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user or not verify_reset_token(data.token, user.hashed_password):
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired")

    user.hashed_password = hash_password(data.new_password)
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Password reset successfully. You can now log in."}


# ── Email verification ────────────────────────────────────────────────────────

class VerifyEmailRequest(BaseModel):
    token: str


@auth_router.post("/send-verification")
async def send_verification(user: User = Depends(get_current_user)):
    """Resend the verification email for the logged-in user."""
    if user.is_verified:
        return {"message": "Email is already verified", "already_verified": True}
    await send_verification_email(user.email, create_email_verify_token(user.id))
    return {"message": "Verification email sent", "already_verified": False}


@auth_router.post("/verify-email")
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Confirm an email address from the link in the verification email."""
    user_id = verify_email_verify_token(data.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Verification link is invalid or has expired")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Verification link is invalid or has expired")

    if not user.is_verified:
        user.is_verified = True
        user.updated_at = datetime.utcnow()
        await db.commit()
    return {"message": "Email verified successfully"}
