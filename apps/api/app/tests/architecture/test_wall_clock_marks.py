"""Every test that asserts on the wall clock carries ``@pytest.mark.wall_clock``.

CI runs the suite on one worker per core, then the ``wall_clock`` tests alone: a duration
measured while three other workers share the machine is not the one the test was written
for (a 0.5 s budget took 0.68 s). A test asserts on the clock when an assert reads it
(``time.perf_counter()``, ``time.monotonic()``, ``time.time()``, their ``_ns`` forms,
``process_time`` and an event loop's ``time()``, the loop however it is named), reads a name
assigned from such a read or from another timed name (``elapsed = end - start``), or calls a
function of the same file that reads it. ``datetime.now()`` and ``utcnow()`` are a clock only
in a difference (``datetime.now() - start``): a timestamp alone is data, not a duration. The
mark may sit on the test, its class, or the module's ``pytestmark``.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
_CLOCK_READS = frozenset(
    {"perf_counter", "perf_counter_ns", "monotonic", "monotonic_ns", "process_time"}
)
_TIME_READS = frozenset({"time", "time_ns"})
_LOOP_GETTERS = frozenset({"get_running_loop", "get_event_loop", "new_event_loop"})
_STAMP_READS = frozenset({"now", "utcnow"})


def _called(node: ast.expr) -> str:
    func = node.func if isinstance(node, ast.Call) else None
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def loop_names(tree: ast.AST) -> frozenset[str]:
    """Names a file gives an event loop: ``lp = asyncio.get_running_loop()``."""
    return frozenset(
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Call)
        and _called(node.value) in _LOOP_GETTERS
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    )


def _is_loop(owner: ast.expr, loops: frozenset[str]) -> bool:
    if isinstance(owner, ast.Call) and _called(owner) in _LOOP_GETTERS:
        return True
    if isinstance(owner, ast.Name) and owner.id in loops:
        return True
    return "loop" in ast.unparse(owner).lower()  # ``self.loop``, an ``event_loop`` fixture


def _is_clock_read(
    call: ast.Call, helpers: frozenset[str], loops: frozenset[str] = frozenset()
) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr in _CLOCK_READS:
            return True
        owner = func.value
        if func.attr == "time" and _is_loop(owner, loops):
            return True  # ``loop.time()``, ``asyncio.get_running_loop().time()``
        return func.attr in _TIME_READS and isinstance(owner, ast.Name) and owner.id == "time"
    if isinstance(func, ast.Name):
        return func.id in _CLOCK_READS or func.id in _TIME_READS or func.id in helpers
    return False


def _is_stamp_read(node: ast.AST) -> bool:
    """``datetime.now()``, ``datetime.datetime.utcnow()``, ``dt.now(UTC)``: a timestamp."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    owner = ast.unparse(node.func.value).lower()
    return node.func.attr in _STAMP_READS and (owner.endswith("datetime") or owner == "dt")


def _reads_clock(
    node: ast.AST, helpers: frozenset[str] = frozenset(), loops: frozenset[str] = frozenset()
) -> bool:
    return any(
        isinstance(sub, ast.Call) and _is_clock_read(sub, helpers, loops) for sub in ast.walk(node)
    )


def _marked(decorators: list[ast.expr]) -> bool:
    return any("wall_clock" in ast.unparse(decorator) for decorator in decorators)


def _module_marked(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets)
        and "wall_clock" in ast.unparse(node.value)
        for node in tree.body
    )


def _difference_of(
    value: ast.expr, timed: set[str], stamps: set[str] | frozenset[str] = frozenset()
) -> bool:
    """``end - start`` with a timed name on either side, or a timestamp on both
    (``datetime.now() - start``): a duration, unlike ``now + 60`` or ``datetime.now() -
    timedelta(days=3)`` (a clock reading used as data, such as a token's expiry)."""

    def stamp(side: ast.expr) -> bool:
        return (isinstance(side, ast.Name) and side.id in stamps) or _is_stamp_read(side)

    return any(
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Sub)
        and (
            any(isinstance(side, ast.Name) and side.id in timed for side in (node.left, node.right))
            or (stamp(node.left) and stamp(node.right))
        )
        for node in ast.walk(value)
    )


def _asserts_on_clock(
    test: ast.FunctionDef | ast.AsyncFunctionDef,
    helpers: frozenset[str],
    loops: frozenset[str] = frozenset(),
) -> bool:
    assigns = [
        node
        for node in ast.walk(test)
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign) and node.value is not None
    ]
    timed: set[str] = set()  # clock readings and durations
    stamps: set[str] = set()  # ``datetime.now()`` readings: a clock only in a difference
    grew = True
    while grew:  # a difference of timed names is a duration: ``elapsed = end - start``
        grew = False
        for node in assigns:
            assert node.value is not None
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
            if _reads_clock(node.value, helpers, loops) or _difference_of(
                node.value, timed, stamps
            ):
                kind = timed
            elif _is_stamp_read(node.value):
                kind = stamps
            else:
                continue
            if not names <= kind:
                kind |= names
                grew = True
    return any(
        isinstance(node, ast.Assert)
        and (
            _reads_clock(node.test, helpers, loops)
            or _difference_of(node.test, timed, stamps)
            or bool({n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)} & timed)
        )
        for node in ast.walk(test)
    )


def unmarked_wall_clock_tests() -> list[str]:
    missing: list[str] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text())
        if _module_marked(tree):
            continue
        loops = loop_names(tree)
        helpers = frozenset(
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and not node.name.startswith("test_")
            and _reads_clock(node, loops=loops)
        )
        scopes: list[tuple[list[ast.expr], list[ast.stmt]]] = [([], tree.body)]
        scopes += [(n.decorator_list, n.body) for n in tree.body if isinstance(n, ast.ClassDef)]
        for class_marks, body in scopes:
            for node in body:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if not node.name.startswith("test_") or _marked(class_marks):
                    continue
                if _asserts_on_clock(node, helpers, loops) and not _marked(node.decorator_list):
                    missing.append(f"{path.relative_to(TESTS)}::{node.name}")
    return missing


def test_every_test_that_times_itself_runs_alone_in_ci() -> None:
    missing = unmarked_wall_clock_tests()
    assert not missing, (
        "asserts on the wall clock, so it runs alone in CI: add @pytest.mark.wall_clock\n  "
        + "\n  ".join(missing)
    )


def test_the_check_sees_a_timed_assert_and_its_helpers() -> None:
    tree = ast.parse(
        "import time\n"
        "def _took(fn):\n    start = time.perf_counter(); fn(); return time.perf_counter() - start\n"
        "def test_direct():\n    t0 = time.monotonic()\n    assert time.monotonic() - t0 < 1\n"
        "def test_named():\n    elapsed = _took(print)\n    assert elapsed < 1\n"
        "def test_plain():\n    now = 3\n    assert now < 4\n"
        # 2026-11-01: a derived name and an event loop's clock were both missed.
        "def test_derived():\n    start = time.monotonic()\n    end = time.monotonic()\n"
        "    elapsed = end - start\n    assert elapsed < 1\n"
        "def test_loop():\n    loop = asyncio.get_running_loop()\n    t0 = loop.time()\n"
        "    assert loop.time() - t0 < 1\n"
        "def test_running_loop():\n    t0 = asyncio.get_running_loop().time()\n"
        "    assert t0 > 0\n"
        # 2026-11-01: a loop under another name, and a datetime difference, were missed.
        "def test_named_loop():\n    lp = asyncio.get_running_loop()\n    t0 = lp.time()\n"
        "    assert lp.time() - t0 < 1\n"
        "def test_datetime_delta():\n    start = datetime.now(UTC)\n    work()\n"
        "    assert (datetime.now(UTC) - start).total_seconds() < 1\n"
        "def test_datetime_elapsed():\n    start = datetime.datetime.utcnow()\n"
        "    elapsed = datetime.datetime.utcnow() - start\n    assert elapsed < limit\n"
        "def test_datetime_stamp():\n    row = make(created=datetime.now(UTC))\n"
        "    stamp = datetime.now(UTC)\n    assert row.created <= stamp\n"
        "    later = datetime.now(UTC) - timedelta(days=3)\n    assert later < stamp\n"
    )
    helpers = frozenset({"_took"})
    loops = loop_names(tree)
    tests = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert _asserts_on_clock(tests["test_direct"], helpers)
    assert _asserts_on_clock(tests["test_named"], helpers)
    assert not _asserts_on_clock(tests["test_plain"], helpers)
    assert _asserts_on_clock(tests["test_derived"], helpers)
    assert _asserts_on_clock(tests["test_loop"], helpers)
    assert _asserts_on_clock(tests["test_running_loop"], helpers)
    assert _asserts_on_clock(tests["test_named_loop"], helpers, loops)
    assert _asserts_on_clock(tests["test_datetime_delta"], helpers)
    assert _asserts_on_clock(tests["test_datetime_elapsed"], helpers)
    assert not _asserts_on_clock(tests["test_datetime_stamp"], helpers)
