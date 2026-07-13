from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt: industry standard for password hashing.
# deprecated="auto" means old schemes are flagged but still verified.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    """
    Create a signed JWT access token.
    Expires in JWT_ACCESS_EXPIRE_MINUTES (default 60).
    """
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """
    Create a signed JWT refresh token.
    Expires in JWT_REFRESH_EXPIRE_DAYS (default 30).
    """
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT.
    Returns the payload dict, or None if invalid/expired.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def verify_access_token(token: str) -> Optional[str]:
    """
    Verify an access token and return the user_id (int).
    Returns None if the token is invalid, expired, or wrong type.
    """
    payload = decode_token(token)
    if not payload:
        return None
    if payload.get("type") != "access":
        return None
    return payload.get("sub")


def verify_refresh_token(token: str) -> Optional[str]:
    """
    Verify a refresh token and return the user_id.
    Returns None if invalid, expired, or wrong type.
    """
    payload = decode_token(token)
    if not payload:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload.get("sub")


# ── Password-reset / email-verification tokens ───────────────────────────────
# Stateless JWTs — no schema changes, nothing stored server-side.
#
# Single-use enforcement for reset tokens: the token embeds a fingerprint of
# the CURRENT password hash. Once the password changes, the fingerprint no
# longer matches and the token is dead — even inside its expiry window. This
# is the standard trick for stateless single-use reset links.

def _pw_fingerprint(hashed_password: Optional[str]) -> str:
    return (hashed_password or "")[-12:]


def create_reset_token(user_id, hashed_password: Optional[str]) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "type": "reset",
        "fp": _pw_fingerprint(hashed_password),
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_reset_token(token: str, hashed_password: Optional[str]) -> Optional[str]:
    """Return the user_id if valid AND the password hasn't changed since issue."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "reset":
        return None
    if payload.get("fp") != _pw_fingerprint(hashed_password):
        return None  # already used (password changed) — single-use guarantee
    return payload.get("sub")


def create_email_verify_token(user_id) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    payload = {
        "sub": str(user_id),
        "type": "verify",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_email_verify_token(token: str) -> Optional[str]:
    payload = decode_token(token)
    if not payload or payload.get("type") != "verify":
        return None
    return payload.get("sub")
