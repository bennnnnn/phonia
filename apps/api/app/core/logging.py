"""Logging configuration: request-id correlation + PII redaction.

``setup_logging`` installs:

- a formatter that appends ``[request_id=<id>]`` to every log line, reading
  the current request ID from ``request_id_context`` (set by
  ``RequestIdMiddleware``) so log lines for a single request can be correlated;
- in production, a JSON formatter (one object per line) so Fly log drains
  can filter on ``event=http_request`` / ``request_id``;
- a filter that redacts emails and bearer/JWT tokens from log messages before
  they hit the handler, so PII never lands in the log sink.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.core.log_context import current_log_ids
from app.core.request_id import request_id_context

# Matches RFC-5321-ish emails (loose: user@host.tld) and common bearer/JWT
# tokens. Redaction is best-effort -- the goal is to keep PII out of the
# default log sink, not to be exhaustive against every encoding.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*")
_REDACTED = "[REDACTED]"

# Fly probes would drown the access log. OPTIONS is CORS preflight noise.
_ACCESS_SKIP_EXACT = frozenset({"/health"})
_ACCESS_SKIP_PREFIXES = ("/health/",)


def _redact_pii(text: str) -> str:
    redacted = _JWT_RE.sub(_REDACTED, text)
    redacted = _BEARER_RE.sub(_REDACTED, redacted)
    return _EMAIL_RE.sub(_REDACTED, redacted)


class _PIIRedactFilter(logging.Filter):
    """Redact emails and bearer/JWT tokens from log records in-place.

    Also redacts ``exc_text`` — Formatters append traceback text after the
    filter runs on ``msg``, so SQL/httpx exception params would otherwise
    leak emails/tokens past this filter.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = _redact_pii(msg)
        if redacted != msg:
            # Replace the formatted message so handlers that re-format see
            # the redacted version too.
            record.msg = redacted
            record.args = ()
        if record.exc_text:
            record.exc_text = _redact_pii(record.exc_text)
        elif record.exc_info:
            # Pre-format so redaction applies before the Formatter caches it.
            record.exc_text = _redact_pii(logging.Formatter().formatException(record.exc_info))
        return True


def _http_access(record: logging.LogRecord) -> tuple[str, str, int, float] | None:
    method = getattr(record, "http_method", None)
    path = getattr(record, "http_path", None)
    status = getattr(record, "http_status", None)
    duration_ms = getattr(record, "duration_ms", None)
    if (
        not isinstance(method, str)
        or not isinstance(path, str)
        or not isinstance(status, int)
        or not isinstance(duration_ms, int | float)
    ):
        return None
    return method, path, status, float(duration_ms)


def _access_line(record: logging.LogRecord) -> str | None:
    access = _http_access(record)
    if access is None:
        return None
    method, path, status, duration_ms = access
    return f"{method} {path} {status} {duration_ms}ms"


def _context_ids() -> dict[str, str]:
    ids: dict[str, str] = {}
    rid = request_id_context.get()
    if rid:
        ids["request_id"] = rid
    ids.update(current_log_ids())
    return ids


class _RequestIdFormatter(logging.Formatter):
    """Formatter that appends ``[request_id=<id> chat_id=<id> ...]`` for the bound ids."""

    _BASE_FMT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    _IDS_FMT = "%(asctime)s %(levelname)s [%(name)s] [%(context_ids)s] %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        access = _access_line(record)
        if access:
            record.msg = access
            record.args = ()
        ids = _context_ids()
        if ids:
            record.context_ids = " ".join(f"{key}={value}" for key, value in ids.items())
            self._style._fmt = self._IDS_FMT
        else:
            self._style._fmt = self._BASE_FMT
        return super().format(record)


class _JsonFormatter(logging.Formatter):
    """One JSON object per line — production / Fly log drains."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_context_ids())
        access = _http_access(record)
        if access is not None:
            method, path, status, duration_ms = access
            payload["event"] = "http_request"
            payload["method"] = method
            payload["path"] = path
            payload["status"] = status
            payload["duration_ms"] = duration_ms
        trace = getattr(record, "turn_trace", None)
        if isinstance(trace, dict):
            # A chat turn's decisions (``modules/chat/turn_trace``): fields, not a string.
            payload["event"] = "turn_trace"
            payload["msg"] = "turn_trace"
            payload["trace"] = trace
        if record.exc_text:
            payload["exc"] = record.exc_text
        elif record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def should_skip_access_log(method: str, path: str) -> bool:
    """True for probes and CORS preflight — not useful in the access log."""
    if method == "OPTIONS":
        return True
    return path in _ACCESS_SKIP_EXACT or path.startswith(_ACCESS_SKIP_PREFIXES)


def log_http_request(
    *,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
) -> None:
    """Emit one structured access line. Never includes query string or body."""
    if should_skip_access_log(method, path):
        return
    logging.getLogger("app.http").info(
        "http_request",
        extra={
            "http_method": method,
            "http_path": path,
            "http_status": status,
            "duration_ms": duration_ms,
        },
    )


def setup_logging(*, json_output: bool = False, level: str = "INFO") -> None:
    formatter: logging.Formatter = _JsonFormatter() if json_output else _RequestIdFormatter()
    root = logging.getLogger()
    # Replace any pre-existing handlers so we don't double-log or keep the
    # default basicConfig handler around.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_PIIRedactFilter())
    root.addHandler(handler)
    root.setLevel(logging.getLevelName(level.upper()) if _known_level(level) else logging.INFO)


def _known_level(level: str) -> bool:
    return isinstance(logging.getLevelName(level.upper()), int)
