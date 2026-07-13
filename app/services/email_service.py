"""
app/services/email_service.py
──────────────────────────────
Zero-dependency SMTP email sender (stdlib smtplib, run off the event loop).

DELIVERY MODES (by configuration, no code changes):
  Dev        — SMTP_HOST=mailpit (docker-compose runs a Mailpit container:
               catches every email, web UI at http://localhost:8025, JSON
               API for tests). Nothing leaves your machine.
  Production — any free SMTP provider:
                 Gmail app password : smtp.gmail.com:587, SMTP_TLS=true
                 Brevo (300/day)    : smtp-relay.brevo.com:587, SMTP_TLS=true
  Unset      — SMTP_HOST empty → emails are logged, never sent. The app
               keeps working; reset links appear in the api logs.

Sending is always best-effort: a mail failure must never fail the HTTP
request that triggered it (especially /auth/forgot-password, which must
return identically whether or not the account exists).
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _send_sync(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send an email. Returns True on success, False otherwise — never raises."""
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — email to %s suppressed.\nSubject: %s\n%s",
                    to, subject, text)
        return False

    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        # smtplib is blocking — hand it to a thread so the event loop stays free
        await asyncio.to_thread(_send_sync, msg)
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as exc:
        logger.error("Email send failed to %s: %s", to, exc)
        return False


# ── App-specific emails ───────────────────────────────────────────────────────

def _button_html(heading: str, body: str, cta_label: str, cta_url: str) -> str:
    return f"""\
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:24px">
  <h2 style="color:#1c1917">{heading}</h2>
  <p style="color:#57534e;line-height:1.6">{body}</p>
  <a href="{cta_url}" style="display:inline-block;margin:16px 0;padding:12px 24px;
     background:#FF6B35;color:#fff;text-decoration:none;border-radius:8px;font-weight:600">
    {cta_label}</a>
  <p style="color:#8a827a;font-size:12px">If the button doesn't work, copy this link:<br>{cta_url}</p>
</div>"""


async def send_password_reset_email(to: str, token: str) -> bool:
    url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    return await send_email(
        to,
        "Reset your ATS-Ready password",
        f"Someone requested a password reset for your ATS-Ready account.\n\n"
        f"Reset it here (valid for {settings.RESET_TOKEN_EXPIRE_MINUTES} minutes):\n{url}\n\n"
        f"If this wasn't you, ignore this email — your password is unchanged.",
        _button_html(
            "Reset your password",
            f"Click below to choose a new password. The link is valid for "
            f"{settings.RESET_TOKEN_EXPIRE_MINUTES} minutes. If you didn't request "
            f"this, you can safely ignore this email.",
            "Reset password", url,
        ),
    )


async def send_verification_email(to: str, token: str) -> bool:
    url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    return await send_email(
        to,
        "Verify your ATS-Ready email",
        f"Welcome to ATS-Ready! Confirm your email address:\n{url}",
        _button_html(
            "Confirm your email",
            "Welcome to ATS-Ready — one click and your account is verified.",
            "Verify email", url,
        ),
    )
