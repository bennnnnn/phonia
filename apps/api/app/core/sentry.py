"""Optional Sentry error reporting, and the never-raising report helpers.

``report_breadcrumb``, ``report_message`` and ``report_exception`` are how
infrastructure records something for Sentry from a best-effort path (a job
that could not be enqueued, a provider that failed). They import the SDK at
call time and swallow any failure: reporting must never break the caller,
and they are no-ops when the SDK is absent or not initialized.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from types import ModuleType
from typing import TYPE_CHECKING, Any, Literal

from app.core.config import Settings
from app.core.log_context import current_log_ids
from app.core.request_id import request_id_context

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

logger = logging.getLogger(__name__)
_initialized = False

# Client hangups are not application errors — they dominate the stream if
# captured at 100%. Keep real exceptions at full sample rate.
_IGNORED_EXC_TYPES = frozenset({"WebSocketDisconnect", "ClientDisconnect"})

_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-forwarded-authorization",
    }
)


def _exception_type_names(event: Event) -> list[str]:
    raw_exc = event.get("exception") or {}
    values = raw_exc.get("values") if isinstance(raw_exc, dict) else None
    names: list[str] = []
    for item in values or []:
        if isinstance(item, dict) and item.get("type"):
            names.append(str(item["type"]))
    return names


def _is_ignored(event: Event, hint: Hint) -> bool:
    exc_info = hint.get("exc_info") if isinstance(hint, dict) else None
    if exc_info and getattr(exc_info[0], "__name__", "") in _IGNORED_EXC_TYPES:
        return True
    return any(name in _IGNORED_EXC_TYPES for name in _exception_type_names(event))


def _scrub_headers(headers: object) -> None:
    if not isinstance(headers, dict):
        return
    for key in list(headers):
        if str(key).lower() in _SENSITIVE_HEADER_NAMES:
            headers[key] = "[REDACTED]"


def _scrub_request(request: object) -> None:
    """Drop bodies and secrets. Chat POSTs must never reach Sentry."""
    if not isinstance(request, dict):
        return
    request.pop("data", None)
    request.pop("cookies", None)
    request["query_string"] = ""
    _scrub_headers(request.get("headers"))
    env = request.get("env")
    if isinstance(env, dict):
        for key in list(env):
            lowered = str(key).lower()
            if lowered in {"http_authorization", "http_cookie"}:
                env[key] = "[REDACTED]"


# Errors can quote what they choked on; keep the start, which says what broke.
_MAX_ERROR_TEXT = 300


def _capped(text: object) -> object:
    if not isinstance(text, str) or len(text) <= _MAX_ERROR_TEXT:
        return text
    return f"{text[:_MAX_ERROR_TEXT]}…"


def _scrub_log_entry(event: Event) -> None:
    """A logged error keeps its template: the arguments are what the user wrote."""
    entry = event.get("logentry")
    if isinstance(entry, dict):
        entry.pop("params", None)
        entry["formatted"] = entry.get("message", "")
    event.pop("extra", None)
    exceptions = event.get("exception")
    values = exceptions.get("values") if isinstance(exceptions, dict) else None
    for value in values or []:
        if isinstance(value, dict) and "value" in value:
            value["value"] = _capped(value["value"])


def before_breadcrumb(crumb: dict[str, Any], hint: Hint) -> dict[str, Any] | None:
    """A log line becomes a breadcrumb as its template, without its arguments or extras."""
    record = hint.get("log_record") if isinstance(hint, dict) else None
    if isinstance(record, logging.LogRecord):
        crumb["message"] = str(record.msg)
        crumb["data"] = {}
    return crumb


def before_send(event: Event, hint: Hint) -> Event | None:
    """Filter noise and strip request bodies, auth headers and logged arguments before upload."""
    if _is_ignored(event, hint):
        return None
    _scrub_request(event.get("request"))
    _scrub_log_entry(event)
    ids = current_log_ids()
    if rid := request_id_context.get():
        ids["request_id"] = rid
    if ids:
        tags = event.setdefault("tags", {})
        if isinstance(tags, dict):
            tags.update(ids)
    return event


Level = Literal["debug", "info", "warning", "error", "fatal"]


def _send(what: str, call: Callable[[ModuleType], object]) -> None:
    try:
        import sentry_sdk

        call(sentry_sdk)
    except Exception:  # never raise into the caller: reporting is best-effort
        logger.debug("Sentry %s not sent", what, exc_info=True)


def report_breadcrumb(
    category: str, message: str, *, level: Level, data: Mapping[str, object]
) -> None:
    _send(
        "breadcrumb",
        lambda sdk: sdk.add_breadcrumb(category=category, message=message, level=level, data=data),
    )


def report_message(message: str, *, level: Level) -> None:
    _send("message", lambda sdk: sdk.capture_message(message, level=level))


def report_exception(message: str) -> None:
    """Capture a synthetic exception named ``message`` (a failure with no traceback to send)."""
    _send("exception", lambda sdk: sdk.capture_exception(Exception(message)))


def init_sentry(settings: Settings) -> None:
    global _initialized
    if _initialized or not settings.sentry_dsn.strip():
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("sentry-sdk not installed; skipping Sentry init")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn.strip(),
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        send_default_pii=False,
        # Frame locals hold prompts, transcripts, memory text and tokens
        # (refresh_token, access_token, id_token). The SDK's scrubber masks
        # only exact names like "token", so stack variables stay off.
        include_local_variables=False,
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
        ignore_errors=list(_IGNORED_EXC_TYPES),
    )
    _initialized = True
    logger.info("Sentry initialized for environment=%s", settings.environment)
