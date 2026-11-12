"""Every API route must require auth unless it is on the explicit public list."""
from fastapi.routing import APIRoute

from app.api.dependencies import get_current_user
from main import app

# (method, path) pairs that are public on purpose.
PUBLIC = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/google"),
    ("GET", "/api/auth/config"),
    ("GET", "/api/billing/plans"),
    ("GET", "/health"),
    ("GET", "/health/ready"),
}


def _depends_on_auth(dependant) -> bool:
    if dependant.call is get_current_user:
        return True
    return any(_depends_on_auth(d) for d in dependant.dependencies)


def test_every_api_route_requires_auth_or_is_allowlisted():
    open_routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(("/api", "/health")):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            if (method, route.path) not in PUBLIC and not _depends_on_auth(route.dependant):
                open_routes.append(f"{method} {route.path}")
    assert not open_routes, f"Unauthenticated routes not on the allowlist: {sorted(open_routes)}"
