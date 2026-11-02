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
``deliver_email`` says why a send failed, so the reminder cycle can wait out a
temporary failure and give up on a refused message instead of retrying it every
minute for two days.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

# Without a provider key, only these environments log the message as if sent.
_MOCK_ENVIRONMENTS = frozenset({"development", "test"})
RESEND_TIMEOUT_SECONDS = 15.0
# Resend's limit for an Idempotency-Key.
_IDEMPOTENCY_KEY_MAX_CHARS = 256


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


class EmailOutcome(StrEnum):
    """What became of one send (``deliver_email``)."""

    SENT = "sent"
    # Not sent, and sending again later may work: no connection, a timeout, a 429, a 5xx,
    # or a refusal of our account or sender (a bad key, an unverified domain), which
    # every message gets until someone fixes the configuration.
    RETRY = "retry"
    # The provider refused this message for good (a bad recipient address or field).
    REJECTED = "rejected"
    # Not attempted: email is off, no provider, no recipient.
    SKIPPED = "skipped"


@dataclass(frozen=True)
class EmailResult:
    outcome: EmailOutcome
    # The provider's Retry-After on a 429, in seconds.
    retry_after: float | None = None

    @property
    def sent(self) -> bool:
        return self.outcome is EmailOutcome.SENT


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
    result = await deliver_email(settings, to=to, subject=subject, html=html, text=text)
    return result.sent


async def deliver_email(
    settings: Settings,
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
    idempotency_key: str | None = None,
) -> EmailResult:
    """Send one email and say what became of it; never raises.

    ``idempotency_key`` (Resend's ``Idempotency-Key``, kept by Resend for a day) makes a
    resend of the same message after a timeout, when Resend had already accepted it,
    return the first send instead of mailing it twice.
    """
    to_label = _recipient_log_label(to)
    if not settings.email_enabled:
        logger.debug("Transactional email disabled; skipping to=%s", to_label)
        return EmailResult(EmailOutcome.SKIPPED)
    if not to.strip():
        logger.warning("Transactional email skipped: empty recipient")
        return EmailResult(EmailOutcome.SKIPPED)

    if not is_configured(settings):
        if not _mocks_without_provider(settings):
            logger.warning(
                "Transactional email not sent (RESEND_API_KEY is not set) to=%s", to_label
            )
            return EmailResult(EmailOutcome.SKIPPED)
        # Dev / no-provider path: log that the flow ran, but not the subject or
        # body. A reminder email's subject is the reminder itself, and
        # transactional emails carry PII that shouldn't sit in INFO logs.
        logger.info(
            "MOCK transactional email to=%s subject_chars=%d chars=%d",
            to_label,
            len(subject),
            len(text),
        )
        return EmailResult(EmailOutcome.SENT)

    payload: dict[str, Any] = {
        "from": settings.email_from,
        "to": to,
        "subject": subject,
        "html": html,
        "text": text,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:_IDEMPOTENCY_KEY_MAX_CHARS]
    try:
        response = await get_pooled_client(RESEND_TIMEOUT_SECONDS).post(
            settings.resend_api_url, json=payload, headers=headers
        )
    except Exception:
        logger.exception("Transactional email send failed to=%s", to_label)
        return EmailResult(EmailOutcome.RETRY)
    return _result(response, to_label)


def _result(response: httpx.Response, to_label: str) -> EmailResult:
    status = response.status_code
    if 200 <= status < 300:
        return EmailResult(EmailOutcome.SENT)
    if status == 409:
        # Resend's answer to an Idempotency-Key it already holds (the first send is done
        # or still going; a resend whose overdue title changed has another body): that
        # message went out under this key, so it is not sent again.
        logger.info("Transactional email already sent under its key to=%s", to_label)
        return EmailResult(EmailOutcome.SENT)
    if status == 429:
        logger.warning("Transactional email throttled to=%s", to_label)
        return EmailResult(EmailOutcome.RETRY, retry_after=_retry_after(response))
    if 400 <= status < 500:
        error_name, message = _error_body(response)
        if _account_or_sender_error(status, error_name, message):
            # Every message gets this answer until the key, sender or domain is fixed:
            # held and tried again, never given up on as if this message were at fault.
            logger.error(
                "Transactional email refused for the account or sender, not the message "
                "(check RESEND_API_KEY and EMAIL_FROM) status=%s name=%s to=%s",
                status,
                error_name,
                to_label,
            )
            return EmailResult(EmailOutcome.RETRY)
        # This message's own fault (a bad address): sent again, it gets the same answer.
        logger.error(
            "Transactional email rejected status=%s name=%s to=%s", status, error_name, to_label
        )
        return EmailResult(EmailOutcome.REJECTED)
    logger.warning("Transactional email provider error status=%s to=%s", status, to_label)
    return EmailResult(EmailOutcome.RETRY)


# Resend answers a key, sender or domain problem with these for any message: 401 and 403
# (missing, invalid or restricted key; a domain not verified), 404 and 405 (a wrong
# ``resend_api_url``). A 400 or 422 is about the request, and a refused sender says so
# in its error ``name`` or names the ``from`` field.
_ACCOUNT_STATUSES = frozenset({401, 403, 404, 405})
_SENDER_ERROR_NAMES = frozenset(
    {
        "invalid_from_address",
        "invalid_access",
        "invalid_region",
        "missing_api_key",
        "invalid_api_key",
        "restricted_api_key",
    }
)
_SENDER_FIELD = re.compile(r"`from`|\bfrom\b field|\bsender\b", re.IGNORECASE)


def _error_body(response: httpx.Response) -> tuple[str, str]:
    """Resend's error ``name`` and ``message`` (empty when the body is not its JSON)."""
    try:
        body = response.json()
    except ValueError:
        return "", ""
    if not isinstance(body, dict):
        return "", ""
    return str(body.get("name") or ""), str(body.get("message") or "")


def _account_or_sender_error(status: int, error_name: str, message: str) -> bool:
    if status in _ACCOUNT_STATUSES or error_name in _SENDER_ERROR_NAMES:
        return True
    return status == 422 and bool(_SENDER_FIELD.search(message))


def _retry_after(response: httpx.Response) -> float | None:
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return None
    return seconds if seconds > 0 else None
