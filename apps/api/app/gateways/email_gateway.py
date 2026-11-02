"""Outbound transactional email gateway.

Provider is Resend (https://resend.com) when ``resend_api_key`` is configured.
With no key in development or test, :func:`send_email` logs the message instead
so the rest of the pipeline (job enqueue, templates, locale selection) is
exercised without any external account. Anywhere else a missing key means the
email is not sent: ``send_email`` returns False, the reminder scheduler does not
start, and the API tells the app email reminders are unavailable. (The mock
used to report success in production too, so reminders were marked sent and
never delivered.) Sending is best-effort: a failure is logged and never raised
into the caller (transactional email must not break auth or the chat path).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

# Without a provider key, only these environments log the message as if sent.
_MOCK_ENVIRONMENTS = frozenset({"development", "test"})
RESEND_TIMEOUT_SECONDS = 15.0


def is_configured(settings: Settings) -> bool:
    return bool(settings.resend_api_key.strip())


def _mocks_without_provider(settings: Settings) -> bool:
    return settings.environment.strip().lower() in _MOCK_ENVIRONMENTS


def can_send(settings: Settings) -> bool:
    """True when ``send_email`` delivers a message (or, in development/test, mocks it)."""
    return settings.email_enabled and (is_configured(settings) or _mocks_without_provider(settings))


def warn_if_unavailable(settings: Settings) -> None:
    """Log once at boot when email is on but this process cannot send any."""
    if settings.email_enabled and not can_send(settings):
        logger.warning(
            "EMAIL_ENABLED=true but RESEND_API_KEY is not set (ENVIRONMENT=%s): welcome, "
            "receipt and reminder emails are not sent and the app hides email reminders. "
            "Set RESEND_API_KEY, or EMAIL_ENABLED=false to silence this.",
            settings.environment,
        )


def _recipient_log_label(to: str) -> str:
    """Domain-only label for logs — never the full mailbox address."""
    at = to.rfind("@")
    if at >= 0 and at + 1 < len(to):
        return f"*@{to[at + 1 :]}"
    return "(invalid-recipient)"


async def send_email(
    settings: Settings,
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
) -> bool:
    """Send one transactional email. Returns True on success, False otherwise.

    Never raises — callers (background jobs) rely on this not propagating.
    """
    to_label = _recipient_log_label(to)
    if not settings.email_enabled:
        logger.debug("Transactional email disabled; skipping to=%s", to_label)
        return False
    if not to.strip():
        logger.warning("Transactional email skipped: empty recipient")
        return False

    if not is_configured(settings):
        if not _mocks_without_provider(settings):
            logger.warning(
                "Transactional email not sent (RESEND_API_KEY is not set) to=%s", to_label
            )
            return False
        # Dev / no-provider path: log that the flow ran, but not the subject or
        # body. A reminder email's subject is the reminder itself, and
        # transactional emails carry PII that shouldn't sit in INFO logs.
        logger.info(
            "MOCK transactional email to=%s subject_chars=%d chars=%d",
            to_label,
            len(subject),
            len(text),
        )
        return True

    payload: dict[str, Any] = {
        "from": settings.email_from,
        "to": to,
        "subject": subject,
        "html": html,
        "text": text,
    }
    try:
        response = await get_pooled_client(RESEND_TIMEOUT_SECONDS).post(
            settings.resend_api_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Transactional email send failed to=%s", to_label)
        return False
