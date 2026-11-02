"""Tests share one fake per family (code-health audit TEST-07).

Copied fakes drifted. Four of nine ``fake_session`` copies were a bare ``AsyncMock()``,
which turns the synchronous ``AsyncSession.add`` into a coroutine, so a test passed even
when the code wrongly awaited it; thirteen session context managers sat beside the shared
one. ``app/tests/fakes.py`` now holds the session, its context manager, the Redis mock and
the user, and ``conftest.py`` the fixtures. This guard:

- keeps ``fake_session`` and the session context manager in that one place: a test that
  needs more (it tracks whether a session is open, say) subclasses ``FakeSessionCM``;
- allows no bare ``AsyncMock()`` Redis: it makes redis-py's synchronous ``pipeline()`` a
  coroutine nobody awaits, and the code under test swallowed the error;
- holds the bare session and user mocks still in the suite at their count, so it only
  goes down: ``fake_session()`` and ``make_user()`` answer as the real objects do.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .boundary_support import APP_ROOT

_TESTS = APP_ROOT / "tests"
_SHARED = frozenset({_TESTS / "fakes.py", _TESTS / "conftest.py", Path(__file__).resolve()})
_BARE_SESSION = re.compile(r"^\s*(?:session|db|mock_session)\s*=\s*AsyncMock\(\)\s*$", re.M)
_BARE_USER = re.compile(r"^\s*user\s*=\s*MagicMock\(\)\s*$", re.M)
_BARE_REDIS = re.compile(
    r"^\s*(?:redis|fake_redis|mock_redis)\s*=\s*AsyncMock\(\)\s*$|\bredis=AsyncMock\(\)", re.M
)
# The bare mocks left; lower these when a change replaces some.
_BARE_SESSIONS = 124
_BARE_USERS = 139


def _test_sources() -> dict[Path, str]:
    return {
        path: path.read_text()
        for path in sorted(_TESTS.rglob("*.py"))
        if path.resolve() not in _SHARED
    }


def test_session_fakes_live_in_fakes_py() -> None:
    copies: list[str] = []
    for path, source in _test_sources().items():
        for node in ast.walk(ast.parse(source)):
            where = f"{path.relative_to(_TESTS)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name == "fake_session":
                    copies.append(f"{where} def fake_session")
            elif isinstance(node, ast.ClassDef) and node.name.endswith("SessionCM"):
                if "FakeSessionCM" not in {ast.unparse(base) for base in node.bases}:
                    copies.append(f"{where} class {node.name}")
    assert copies == [], "use fake_session / FakeSessionCM from app/tests/fakes.py"


def test_no_bare_redis_mock() -> None:
    bare = [
        f"{path.relative_to(_TESTS)}:{source.count(chr(10), 0, match.start()) + 1}"
        for path, source in _test_sources().items()
        for match in _BARE_REDIS.finditer(source)
    ]
    assert bare == [], "use redis_mock() from app/tests/fakes.py, or the fake_redis fixture"


def test_bare_session_and_user_mocks_only_go_down() -> None:
    sources = _test_sources().values()
    sessions = sum(len(_BARE_SESSION.findall(source)) for source in sources)
    users = sum(len(_BARE_USER.findall(source)) for source in sources)
    assert sessions <= _BARE_SESSIONS, "a new bare session mock: use fake_session()"
    assert users <= _BARE_USERS, "a new bare user mock: use make_user()"
    assert (sessions, users) == (_BARE_SESSIONS, _BARE_USERS), (
        f"fewer bare mocks now: set _BARE_SESSIONS = {sessions} and _BARE_USERS = {users}"
    )
