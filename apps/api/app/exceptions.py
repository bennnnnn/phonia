"""Exceptions shared across modules, and the one shape every refusal takes."""

from __future__ import annotations

from collections.abc import Mapping

# Over a request limit, any route's: the phone words it in its own language.
RATE_LIMITED_CODE = "rate_limited"

# The code a refusal falls back to when its raise site names none: what kind it is.
_STATUS_CODES = {
    400: "invalid",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    410: "expired",
    413: "too_large",
    415: "unsupported_type",
    422: "invalid",
    429: RATE_LIMITED_CODE,
    500: "failed",
    501: "not_supported",
    502: "upstream_failed",
    503: "unavailable",
}


class DomainError(Exception):
    """A refusal a service makes: English to show, and the code a client reads.

    Modules raised errors carrying HTTP fields in four styles, and the phone recovered
    their meaning by matching the English (code-health audit DUP-10). A module
    subclasses this; the app's one handler (``core/domain_errors.py``) answers
    ``status_code`` with ``{"detail": {"code": ..., "message": ..., **fields}}``. A
    client switches on ``code``; rewording ``message`` breaks nothing.
    """

    status_code = 400
    default_code: str | None = None

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        headers: Mapping[str, str] | None = None,
        **fields: object,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.code = code or self.default_code or _STATUS_CODES.get(self.status_code, "refused")
        self.headers = dict(headers or {})
        self.fields = fields

    @property
    def detail(self) -> str:
        """The English, as a route's ``HTTPException`` carried it."""
        return self.message

    def body(self) -> dict[str, object]:
        """The response's ``detail``."""
        return {"code": self.code, "message": self.message, **self.fields}


class RateLimitedError(DomainError):
    """Over a request limit: 429 ``rate_limited``, with the wait in ``Retry-After``.

    A limit answered with an ``HTTPException`` sent English alone: a chat read it as
    "Couldn't reach the server", a scan or a dictation showed the English.
    """

    status_code = 429
    default_code = RATE_LIMITED_CODE

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message, headers={"Retry-After": str(retry_after_seconds)})


class AuthenticationError(Exception):
    """A sign-in or a token the server does not accept; the API answers 401.

    Google, Apple, the access and refresh tokens and dev login all raise it. It was the
    Google gateway's ``GoogleAuthError``, so ``core`` took its auth error from a Google
    module and a revoked JWT read as a Google failure (code-health audit CLAR-14).

    A sign-in's refusal names ``code`` (``google_token_invalid``): the login screen words
    it in the phone's language, never the English (``modules/account/signin_refusals.py``).
    """

    def __init__(self, *args: object, code: str | None = None) -> None:
        super().__init__(*args)
        self.code = code


class ChatServiceError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class QuotaExceededError(ChatServiceError):
    pass


class SpendCapReachedError(ChatServiceError):
    """Today's global spend cap (``DAILY_GLOBAL_SPEND_USD``) is reached; no turn starts.

    Not a ``QuotaExceededError``: the user's own allowance is not used up, so
    the transports send the plain error event (this message), not the quota
    code that opens the upgrade prompt. ``fields`` (``feature``) go on the event:
    a picture's cap is worded as the picture's, not as every message paused.
    """

    def __init__(self, message: str, **fields: str) -> None:
        super().__init__(message)
        self.fields = fields


class ChatNotFoundError(ChatServiceError):
    pass


class TurnRefusedError(ChatServiceError):
    """A turn a feature refused with its own code ("daily_limit", "content_blocked").

    The chat transports send that code and any ``fields`` (``feature``) on the error
    event, so the phone says which limit it was instead of "out of messages".
    """

    def __init__(self, message: str, *, code: str, **fields: str) -> None:
        super().__init__(message)
        self.code = code
        self.fields = fields


class ChatBusyError(ChatServiceError):
    """Another turn is already preparing/streaming on this chat.

    Transports map this to ``code: "busy"`` (same as same-socket rejection).
    """

    def __init__(
        self,
        message: str = "Still generating — wait or cancel first.",
    ) -> None:
        super().__init__(message)


class AttachmentValidationError(ChatServiceError):
    pass


class ConsentRequiredError(ChatServiceError):
    """The account has not agreed to what goes to outside AI services, or withdrew.

    Chat transports send ``code: "consent_required"`` and HTTP answers 403 with
    the same code; the phone opens its consent screen (``core/consent.py``).
    """

    code = "consent_required"

    def __init__(
        self,
        message: str = "Agree to how Recall uses outside AI services to continue.",
    ) -> None:
        super().__init__(message)


class UnknownModelOverrideError(ChatServiceError):
    """Per-message picker asked for an alias the user's pool does not include."""

    def __init__(self, alias: str) -> None:
        self.alias = alias
        super().__init__(f"Unknown or unavailable model: {alias}")


class RedisUnavailableError(Exception):
    """Redis is required for auth revocation / quota; outage → fail closed with 503.

    Distinct from ChatServiceError so transports can return ``unavailable`` / 503
    with Retry-After instead of a generic 500 or a misleading 401.
    """

    def __init__(
        self,
        message: str = "Service temporarily unavailable. Please retry shortly.",
    ) -> None:
        self.message = message
        super().__init__(message)


class PushTokenBindError(Exception):
    """Cross-user push-token rebind rejected (missing or mismatched device_id)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
