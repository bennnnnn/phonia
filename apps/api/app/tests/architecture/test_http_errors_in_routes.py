"""Services refuse with a ``DomainError``; only the HTTP layer speaks ``HTTPException``.

Services raised HTTP errors themselves (speech, scan reads, consent, uploads), which
the tool loop and the WebSocket path also call, and their refusals reached clients as
English only (code-health audit DUP-10). A route file (``api.py``, ``*_api.py``), a
legacy router or ``core/`` may still raise one for a request-shaped failure.
"""

from __future__ import annotations

import ast

from .boundary_support import APP_ROOT


def _imports_http_exception(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "fastapi",
            "fastapi.exceptions",
            "starlette.exceptions",
        }:
            if any(alias.name == "HTTPException" for alias in node.names):
                return True
    return False


def _is_http_layer(relative: str) -> bool:
    name = relative.rsplit("/", 1)[-1]
    return (
        name == "api.py"
        or name.endswith("_api.py")
        or relative.startswith(("routers/", "core/"))
        # The app, and the worker's own health probe app.
        or relative in {"main.py", "worker_health.py"}
    )


def test_the_guard_sees_an_import() -> None:
    assert _imports_http_exception("from fastapi import Depends, HTTPException\n")
    assert not _imports_http_exception("from fastapi import Depends\n")


def test_only_the_http_layer_raises_http_errors() -> None:
    found = [
        relative
        for path in sorted(APP_ROOT.rglob("*.py"))
        if "tests" not in (relative_path := path.relative_to(APP_ROOT)).parts
        and not _is_http_layer(relative := str(relative_path))
        and _imports_http_exception(path.read_text())
    ]
    assert not found, "Raise a DomainError subclass (app/exceptions.py) instead:\n" + "\n".join(
        found
    )
