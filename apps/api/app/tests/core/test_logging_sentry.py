import json
import logging
from unittest.mock import MagicMock
from uuid import uuid4

from app.core.config import Settings
from app.core.logging import (
    _JsonFormatter,
    _PIIRedactFilter,
    _RequestIdFormatter,
    log_http_request,
    setup_logging,
    should_skip_access_log,
)
from app.core.request_id import request_id_context
from app.core.sentry import before_breadcrumb, before_send, init_sentry


def test_setup_logging_configures_root_logger_level():
    """setup_logging must set the root logger to INFO level."""
    root = logging.getLogger()
    prior_level = root.level
    prior_handlers = list(root.handlers)
    try:
        setup_logging()
        assert root.level == logging.INFO
    finally:
        root.setLevel(prior_level)
        root.handlers = prior_handlers


def test_setup_logging_installs_handler_with_formatter_and_filter():
    """setup_logging must install a handler carrying the request-id formatter
    and the PII redaction filter — the two things that make logs safe to ship."""
    root = logging.getLogger()
    # Snapshot existing handlers so we can restore them after the test.
    prior = list(root.handlers)
    try:
        setup_logging()
        assert root.handlers, "expected at least one handler after setup_logging"
        has_formatter = any(isinstance(h.formatter, _RequestIdFormatter) for h in root.handlers)
        has_filter = any(
            any(isinstance(f, _PIIRedactFilter) for f in h.filters) for h in root.handlers
        )
        assert has_formatter, "no handler carries _RequestIdFormatter"
        assert has_filter, "no handler carries _PIIRedactFilter"
    finally:
        root.handlers = prior


def test_pii_redact_filter_redacts_emails():
    """Emails in log messages must be replaced with [REDACTED]."""
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="user alice@example.com logged in",
        args=(),
        exc_info=None,
    )
    _PIIRedactFilter().filter(rec)
    assert "alice@example.com" not in rec.getMessage()
    assert "[REDACTED]" in rec.getMessage()


def test_pii_redact_filter_redacts_bearer_tokens():
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="auth: Bearer abc.def.ghi",
        args=(),
        exc_info=None,
    )
    _PIIRedactFilter().filter(rec)
    assert "Bearer abc.def.ghi" not in rec.getMessage()
    assert "[REDACTED]" in rec.getMessage()


def test_pii_redact_filter_redacts_jwt_tokens():
    """Raw JWTs (eyJ...) must be redacted even without a 'Bearer' prefix."""
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature",
        args=(),
        exc_info=None,
    )
    _PIIRedactFilter().filter(rec)
    assert "eyJhbGciOiJIUzI1NiJ9" not in rec.getMessage()
    assert "[REDACTED]" in rec.getMessage()


def test_pii_redact_filter_redacts_exc_text_emails():
    """Emails in formatted exception text must be redacted (not only msg)."""
    rec = logging.LogRecord(
        name="t",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="db failed",
        args=(),
        exc_info=None,
    )
    rec.exc_text = "IntegrityError: duplicate key for alice@example.com"
    _PIIRedactFilter().filter(rec)
    assert rec.exc_text is not None
    assert "alice@example.com" not in rec.exc_text
    assert "[REDACTED]" in rec.exc_text


def test_pii_redact_filter_redacts_exc_info_traceback():
    """When only exc_info is set, pre-format and redact before Formatter caches it."""
    try:
        raise ValueError("failed for bob@example.com")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
    rec = logging.LogRecord(
        name="t",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="boom",
        args=(),
        exc_info=exc_info,
    )
    _PIIRedactFilter().filter(rec)
    assert rec.exc_text is not None
    assert "bob@example.com" not in rec.exc_text
    assert "[REDACTED]" in rec.exc_text


def test_request_id_formatter_includes_request_id_when_set():
    """When request_id_context is set, the formatter must include it in the line."""
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    token = request_id_context.set("req-abc-123")
    try:
        line = _RequestIdFormatter().format(rec)
    finally:
        request_id_context.reset(token)
    assert "request_id=req-abc-123" in line
    assert "hello" in line


def test_request_id_formatter_omits_request_id_when_unset():
    """When no request ID is in context, the formatter must NOT add the field."""
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    # Ensure no request ID is set in this context.
    token = request_id_context.set(None)
    try:
        line = _RequestIdFormatter().format(rec)
    finally:
        request_id_context.reset(token)
    assert "request_id=" not in line
    assert "hello" in line


def test_init_sentry_noops_without_dsn():
    init_sentry(Settings(sentry_dsn=""))


def test_init_sentry_handles_missing_sdk(monkeypatch):
    import app.core.sentry as sentry_mod

    monkeypatch.setattr(sentry_mod, "_initialized", False)
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("no sentry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    sentry_mod.init_sentry(Settings(sentry_dsn="https://example@sentry.io/1"))


def test_init_sentry_initializes_when_configured(monkeypatch):
    import app.core.sentry as sentry_mod

    monkeypatch.setattr(sentry_mod, "_initialized", False)
    init_mock = MagicMock()
    fake_sdk = MagicMock()
    fake_sdk.init = init_mock
    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", fake_sdk)
    monkeypatch.setitem(
        __import__("sys").modules,
        "sentry_sdk.integrations.fastapi",
        MagicMock(FastApiIntegration=MagicMock()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "sentry_sdk.integrations.starlette",
        MagicMock(StarletteIntegration=MagicMock()),
    )

    sentry_mod.init_sentry(Settings(sentry_dsn="https://example@sentry.io/1", environment="test"))

    init_mock.assert_called_once()
    kwargs = init_mock.call_args.kwargs
    assert kwargs["before_send"] is sentry_mod.before_send
    assert kwargs["before_breadcrumb"] is sentry_mod.before_breadcrumb
    assert kwargs["send_default_pii"] is False
    assert kwargs["include_local_variables"] is False
    assert "WebSocketDisconnect" in kwargs["ignore_errors"]
    assert sentry_mod._initialized is True


def test_sentry_error_events_carry_no_frame_locals(monkeypatch):
    """A crash in the chat or token path must not upload the prompt or a token.

    The SDK attaches every frame's local variables by default; its scrubber
    only masks exact names such as ``token``, so ``refresh_token``,
    ``access_token`` and message text went out with the stack trace.
    """
    import sentry_sdk
    from sentry_sdk.transport import Transport

    import app.core.sentry as sentry_mod

    captured: dict = {}
    monkeypatch.setattr(sentry_mod, "_initialized", False)
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))
    sentry_mod.init_sentry(Settings(sentry_dsn="https://public@example.com/1"))
    options = {
        key: value
        for key, value in captured.items()
        if key not in {"integrations", "dsn", "before_send", "before_breadcrumb"}
    }

    events: list[dict] = []

    class _Capture(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.type == "event":
                    events.append(item.payload.json)

    client = sentry_sdk.Client(
        dsn="https://public@example.com/1",
        transport=_Capture,
        default_integrations=False,
        **options,
    )

    # Built at runtime: the event's source-context lines must not be what
    # carries them.
    secret_token = "rt-" + uuid4().hex
    secret_prompt = "my bank pin is " + uuid4().hex

    def stream_turn(refresh_token: str, prompt: str) -> None:
        raise RuntimeError("boom")

    with sentry_sdk.isolation_scope() as scope:
        scope.set_client(client)
        try:
            stream_turn(secret_token, secret_prompt)
        except RuntimeError:
            sentry_sdk.capture_exception()
    client.flush(timeout=2)

    assert events, "the exception was not captured"
    serialized = json.dumps(events)
    assert "stream_turn" in serialized
    assert secret_token not in serialized
    assert secret_prompt not in serialized


def test_setup_logging_json_output_uses_json_formatter():
    root = logging.getLogger()
    prior = list(root.handlers)
    try:
        setup_logging(json_output=True)
        assert any(isinstance(h.formatter, _JsonFormatter) for h in root.handlers)
    finally:
        root.handlers = prior


def test_json_formatter_includes_request_id_and_access_fields():
    rec = logging.LogRecord(
        name="app.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    rec.http_method = "GET"
    rec.http_path = "/legal/privacy"
    rec.http_status = 200
    rec.duration_ms = 4.2
    token = request_id_context.set("req-json-1")
    try:
        line = _JsonFormatter().format(rec)
    finally:
        request_id_context.reset(token)
    payload = json.loads(line)
    assert payload["event"] == "http_request"
    assert payload["method"] == "GET"
    assert payload["path"] == "/legal/privacy"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 4.2
    assert payload["request_id"] == "req-json-1"


def test_should_skip_access_log_health_and_options():
    assert should_skip_access_log("GET", "/health") is True
    assert should_skip_access_log("GET", "/health/ready") is True
    assert should_skip_access_log("OPTIONS", "/legal/privacy") is True
    assert should_skip_access_log("GET", "/legal/privacy") is False


def test_log_http_request_emits_extras(caplog):
    caplog.set_level(logging.INFO, logger="app.http")
    log_http_request(method="GET", path="/legal/privacy", status=200, duration_ms=3.1)
    records = [r for r in caplog.records if r.name == "app.http"]
    assert records
    assert records[0].http_method == "GET"
    assert records[0].http_path == "/legal/privacy"
    assert records[0].http_status == 200
    assert records[0].duration_ms == 3.1


def test_log_http_request_skips_health(caplog):
    caplog.set_level(logging.INFO, logger="app.http")
    log_http_request(method="GET", path="/health", status=200, duration_ms=1.0)
    assert not [r for r in caplog.records if r.name == "app.http"]


def test_before_send_drops_websocket_disconnect():
    event = {"exception": {"values": [{"type": "WebSocketDisconnect", "value": "1000"}]}}
    assert before_send(event, {}) is None


def test_before_send_drops_client_disconnect_from_hint():
    class ClientDisconnect(Exception):
        pass

    event = {"exception": {"values": [{"type": "ValueError"}]}}
    assert before_send(event, {"exc_info": (ClientDisconnect, ClientDisconnect(), None)}) is None


def test_before_send_keeps_real_errors_and_scrubs_request():
    event = {
        "exception": {"values": [{"type": "RuntimeError", "value": "boom"}]},
        "request": {
            "url": "http://test/chats",
            "data": {"content": "secret chat body"},
            "cookies": {"session": "abc"},
            "query_string": "token=abc",
            "headers": {
                "Authorization": "Bearer secret",
                "Content-Type": "application/json",
            },
            "env": {"HTTP_AUTHORIZATION": "Bearer secret"},
        },
    }
    token = request_id_context.set("req-sentry-1")
    try:
        kept = before_send(event, {})
    finally:
        request_id_context.reset(token)
    assert kept is event
    assert "data" not in kept["request"]
    assert "cookies" not in kept["request"]
    assert kept["request"]["query_string"] == ""
    assert kept["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert kept["request"]["headers"]["Content-Type"] == "application/json"
    assert kept["request"]["env"]["HTTP_AUTHORIZATION"] == "[REDACTED]"
    assert kept["tags"]["request_id"] == "req-sentry-1"


def test_report_helpers_reach_the_sdk(monkeypatch):
    import sentry_sdk

    from app.core import sentry

    calls: list[tuple[str, tuple, dict]] = []
    for name in ("add_breadcrumb", "capture_message", "capture_exception"):
        monkeypatch.setattr(sentry_sdk, name, lambda *a, _n=name, **kw: calls.append((_n, a, kw)))
    sentry.report_breadcrumb("jobs.queue", "status", level="info", data={"dlq": 1})
    sentry.report_message("DLQ deep", level="warning")
    sentry.report_exception("enqueue_failed:memory")

    assert calls[0] == (
        "add_breadcrumb",
        (),
        {"category": "jobs.queue", "message": "status", "level": "info", "data": {"dlq": 1}},
    )
    assert calls[1] == ("capture_message", ("DLQ deep",), {"level": "warning"})
    name, args, _ = calls[2]
    assert name == "capture_exception"
    assert str(args[0]) == "enqueue_failed:memory"


def test_report_helpers_never_raise_without_the_sdk(monkeypatch):
    import sys

    from app.core import sentry

    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # `import sentry_sdk` raises
    sentry.report_breadcrumb("push.token", "rebound", level="warning", data={})
    sentry.report_message("x", level="warning")
    sentry.report_exception("y")


def test_the_access_line_logs_the_route_template_not_the_path(caplog):
    """A memory area's slug is made from its name: the raw path carries the user's words."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.request_id import RequestIdMiddleware

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.delete("/memories/documents/{topic}")
    async def forget(topic: str) -> dict[str, str]:
        return {}

    caplog.set_level(logging.INFO, logger="app.http")
    assert TestClient(app).delete("/memories/documents/area:my-divorce").status_code == 200
    paths = [r.http_path for r in caplog.records if r.name == "app.http"]
    assert paths == ["/memories/documents/{topic}"]


def test_before_send_keeps_a_logged_errors_template_only():
    reminder = "take sertraline at 9"
    event = {
        "logentry": {
            "message": "Send failed subject=%s",
            "formatted": f"Send failed subject={reminder}",
            "params": [reminder],
        },
        "extra": {"subject": reminder},
        "exception": {"values": [{"type": "StatementError", "value": "x" * 1_000}]},
    }
    kept = before_send(event, {})
    assert kept is not None
    assert kept["logentry"] == {
        "message": "Send failed subject=%s",
        "formatted": "Send failed subject=%s",
    }
    assert "extra" not in kept
    assert len(kept["exception"]["values"][0]["value"]) == 301


def test_before_breadcrumb_drops_a_log_lines_arguments():
    reminder = "call the lawyer"
    record = logging.LogRecord(
        "app.todos", logging.INFO, __file__, 1, "saved title=%s", (reminder,), None
    )
    crumb = {
        "message": f"saved title={reminder}",
        "data": {"title": reminder},
        "category": "app.todos",
    }
    kept = before_breadcrumb(crumb, {"log_record": record})
    assert kept == {"message": "saved title=%s", "data": {}, "category": "app.todos"}


def test_logged_user_text_never_reaches_sentry():
    """Through the real SDK: an INFO line becomes a breadcrumb, an ERROR line an event."""
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.transport import Transport

    events: list[dict] = []

    class _Capture(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.type == "event":
                    events.append(item.payload.json)

    client = sentry_sdk.Client(
        dsn="https://public@example.com/1",
        transport=_Capture,
        default_integrations=False,
        integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
    )
    reminder = "call the clinic about the results " + uuid4().hex
    log = logging.getLogger("app.tests.sentry_privacy")
    previous = log.level
    log.setLevel(logging.INFO)
    try:
        with sentry_sdk.isolation_scope() as scope:
            scope.set_client(client)
            log.info("To-do saved title=%s", reminder)
            log.error("Reminder email failed subject=%s", reminder)
        client.flush(timeout=2)
    finally:
        log.setLevel(previous)

    assert events, "the logged error was not captured"
    serialized = json.dumps(events)
    assert "Reminder email failed subject=%s" in serialized
    assert "To-do saved title=%s" in serialized
    assert reminder not in serialized
