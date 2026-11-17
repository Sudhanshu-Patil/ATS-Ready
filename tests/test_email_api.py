"""Email over HTTPS (Brevo / Resend): Render's free plan blocks SMTP, so production cannot use it."""
import httpx

from app.config import settings
from app.services import email_service


class FakeResponse:
    def __init__(self, status=201):
        self.status_code, self.request = status, httpx.Request("POST", "https://x")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=self.request, response=httpx.Response(self.status_code))


def capture(monkeypatch, status=201):
    seen = {}

    async def fake_post(self, url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(status)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return seen


async def test_brevo_api_is_used_over_https(monkeypatch):
    seen = capture(monkeypatch)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "key-1")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "ATS-Ready <me@example.com>")
    assert await email_service.send_email("you@example.org", "Hi", "text body", "<p>html</p>") is True
    assert seen["url"] == "https://api.brevo.com/v3/smtp/email" and seen["headers"] == {"api-key": "key-1"}
    assert seen["json"]["sender"] == {"name": "ATS-Ready", "email": "me@example.com"}
    assert seen["json"]["to"] == [{"email": "you@example.org"}] and seen["json"]["htmlContent"] == "<p>html</p>"


async def test_resend_api_is_used_when_brevo_is_not_set(monkeypatch):
    seen = capture(monkeypatch)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re-1")
    assert await email_service.send_email("you@example.org", "Hi", "text") is True
    assert seen["url"] == "https://api.resend.com/emails" and seen["headers"] == {"Authorization": "Bearer re-1"}


async def test_a_failing_provider_returns_false_and_never_raises(monkeypatch):
    capture(monkeypatch, status=401)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "bad")
    assert await email_service.send_email("you@example.org", "Hi", "text") is False
