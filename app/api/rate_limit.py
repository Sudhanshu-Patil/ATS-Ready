"""
app/api/rate_limit.py
──────────────────────
Per-IP rate limiting for auth endpoints (register/login/password-reset/
verification-email) — the classic brute-force / credential-stuffing /
email-bombing surface that had zero protection.

Backed by Redis so limits are shared across the api + worker processes and
survive restarts. Auto-disabled under pytest so the test suite's rapid-fire
register/login calls from a single synthetic client address never trip it.
Detected via sys.modules rather than the PYTEST_CURRENT_TEST env var — that
var is only set once a test starts *running*, but this module is imported
at collection time (conftest.py does `from main import app` up top), before
any test has started — so an env-var check would still see it as unset.
"""
import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

_DISABLED = "pytest" in sys.modules

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    enabled=not _DISABLED,
)
