"""No log line at INFO or above carries what the user wrote.

INFO and above reach the log drain and Sentry (breadcrumbs, and events from ERROR), where
retention and access differ from the database's. A reminder's title went out as
``title=%s`` and a reminder email's subject, the reminder itself, as ``subject=%r``. A log
call says how much instead: ``title_chars=%d`` with ``len(title)``, ids and kinds.

The check reads each logger call's arguments for a name that holds user or model text.
``len()``, ``type()`` and ``.__name__`` around it are fine, and so is a provider's error
body (``response.text``), which is the provider's words, not the user's.
"""

from __future__ import annotations

import ast
import re

from .boundary_support import APP_ROOT

_LEVELS = frozenset({"info", "warning", "warn", "error", "exception", "critical"})
_TEXT_NAMES = re.compile(
    r"^(?:content|title|subject|text|prompt|query|transcript|question|summary|snippet|caption"
    r"|reply|answer|message|instruction|expr|expression|fact|note|description|raw|html)$"
    r"|_(?:content|title|subject|text|prompt|query|transcript|question|summary|reply|answer)$",
    re.IGNORECASE,
)
_WRAPPERS_THAT_HIDE = frozenset({"len", "type", "bool", "id", "isinstance"})
_PROVIDER_RESPONSES = frozenset({"response", "resp"})
# (file, name): why the name holds no user text there.
_ALLOWED = {
    ("services/scan_read.py", "subject"): "the STEM subject's name: maths, physics, chemistry",
    ("background/handlers.py", "raw"): "a job payload's malformed user id",
    ("gateways/revenuecat_gateway.py", "raw"): "a RevenueCat webhook field (a timestamp)",
}


def _names(node: ast.AST) -> set[str]:
    """Identifiers an argument reads, leaving out what a wrapper reduces to a size or a type."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in _WRAPPERS_THAT_HIDE:
            return set()
    if isinstance(node, ast.Attribute):
        if node.attr == "__name__":
            return set()
        if isinstance(node.value, ast.Name) and node.value.id in _PROVIDER_RESPONSES:
            return set()
        return {node.attr} | _names(node.value)
    if isinstance(node, ast.Name):
        return {node.id}
    found: set[str] = set()
    for child in ast.iter_child_nodes(node):
        found |= _names(child)
    return found


def _is_log_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LEVELS
        and "log" in ast.unparse(node.func.value).lower()
        and bool(node.args)
    )


def test_no_log_line_carries_user_text() -> None:
    leaks = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative.startswith("tests/"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not _is_log_call(node):
                continue
            assert isinstance(node, ast.Call)
            for name in sorted({name for arg in node.args[1:] for name in _names(arg)}):
                if _TEXT_NAMES.search(name) and (relative, name) not in _ALLOWED:
                    leaks.append(f"{relative}:{node.lineno} logs {name}")
    assert not leaks, "log its length or an id instead:\n" + "\n".join(leaks)


def test_the_check_sees_a_leak_and_passes_a_length() -> None:
    def leaked(source: str) -> set[str]:
        call = ast.parse(source).body[0]
        assert isinstance(call, ast.Expr) and _is_log_call(call.value)
        assert isinstance(call.value, ast.Call)
        return {n for arg in call.value.args[1:] for n in _names(arg) if _TEXT_NAMES.search(n)}

    assert leaked('logger.info("saved title=%s", title[:80])') == {"title"}
    assert leaked('logger.exception("failed subject=%r", email.subject)') == {"subject"}
    assert leaked('logger.info("saved title_chars=%d", len(title))') == set()
    assert leaked('logger.info("skipped: %s", type(exc).__name__)') == set()
    assert leaked('logger.warning("failed body=%s", response.text[:500])') == set()
