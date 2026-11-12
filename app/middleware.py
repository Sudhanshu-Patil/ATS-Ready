"""Security headers and request-body size limit (pure ASGI, no extra deps)."""
import base64
import hashlib
import re
from pathlib import Path

MAX_BODY_BYTES = 6 * 1024 * 1024        # a bit above the 5 MB resume upload cap
DIST_INDEX = Path(__file__).parent / "static" / "dist" / "index.html"


def _inline_script_hashes() -> str:
    """CSP hashes for the inline scripts in the built index.html (the theme
    bootstrap), so script-src does not need 'unsafe-inline'."""
    try:
        html = DIST_INDEX.read_text(encoding="utf-8")
    except OSError:
        return ""
    hashes = []
    for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, flags=re.S):
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return " ".join(hashes)


def build_csp() -> str:
    script = " ".join(filter(None, ["'self'", "https://accounts.google.com", _inline_script_hashes()]))
    return "; ".join([
        "default-src 'self'",
        f"script-src {script}",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: https:",
        "connect-src 'self' https://accounts.google.com https://*.ingest.sentry.io https://*.ingest.us.sentry.io",
        "frame-src https://accounts.google.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
        self.headers = [
            (b"content-security-policy", build_csp().encode()),
            (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message["headers"]}
                message["headers"] = list(message["headers"]) + [
                    h for h in self.headers if h[0] not in present]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    """413 when a request body exceeds max_bytes: by Content-Length up front,
    and by counting bytes for chunked uploads that omit it."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            return await self._reject(send)

        seen = 0
        exceeded = started = False

        async def limited_receive():
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    exceeded = True
                    return {"type": "http.disconnect"}   # the app stops reading
            return message

        async def tracking_send(message):
            nonlocal started
            if exceeded:
                return                                    # drop whatever the aborted app says
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        finally:
            if exceeded and not started:
                await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = b'{"detail":"Request body too large."}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


class RequestLogMiddleware:
    """Request id (accepted from the proxy or generated), echoed in X-Request-ID,
    bound to every log line of the request, plus one access-log line with the
    duration. Health checks are skipped so uptime pings don't flood the logs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        import time
        import uuid
        import structlog

        raw = dict(scope["headers"]).get(b"x-request-id", b"").decode()[:64]
        rid = raw if raw.isalnum() or raw.replace("-", "").isalnum() and raw else uuid.uuid4().hex[:16]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        started, status = time.monotonic(), 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message["headers"]) + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            if not scope["path"].startswith("/health"):
                structlog.get_logger("access").info(
                    "request", method=scope["method"], path=scope["path"], status=status,
                    ms=int((time.monotonic() - started) * 1000))
