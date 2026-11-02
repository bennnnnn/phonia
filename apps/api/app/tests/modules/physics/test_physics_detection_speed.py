"""Physics detection runs on every chat turn, so it must stay linear and cheap.

Each regex used to retry a digit run from every digit, or a whole-text
lookahead from every position: a 3,000-character paste cost 0.7 s per turn and
12,000 cost 11.5 s. The budgets below are loose on purpose. A linear pattern
finishes in a few milliseconds; a quadratic one takes seconds, so the test
fails clearly without flaking on a slow runner.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import time

import pytest

import app.modules.physics as physics_package
from app.modules.physics import extract
from app.modules.physics.extractors.circuit_patterns import resistor_values
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.solvers.arithmetic import quadratic_roots
from app.services.symbolic_text import _MAX_PHYSICS_REQUEST, _MAX_SUBJECT_TEXT

_PATTERN_BUDGET_SECONDS = 0.15
_CALL_BUDGET_SECONDS = 0.5

_REPORT = (
    "The quarterly report shows revenue grew 12 percent to 3.4 million while costs "
    "fell 5 percent. Team A shipped 14 features and 3 bug fixes in 2 weeks. "
)

# Each shape once made at least one physics pattern quadratic.
_SHAPES = {
    "digit run": "1",
    "spaced digits": "1 ",
    "decimals": "1.1",
    "words": "a ",
    "report": _REPORT,
    "angles": "30 degrees ",
    "forces": "1 N ",
    "masses": "mass 7 kg ",
    "speeds": "speed 7 m/s ",
    "spring constant": "k = ",
    "power": "power 1 J ",
    "resistor list": "1, 2 and 3 ",
}


def _repeat(shape: str, size: int) -> str:
    return (shape * (size // len(shape) + 1))[:size]


def _csv(size: int) -> str:
    return ", ".join(str(index % 97) for index in range(size))[:size]


_NAMES = (*_SHAPES, "csv")


def _text(name: str, size: int) -> str:
    return _csv(size) if name == "csv" else _repeat(_SHAPES[name], size)


def _physics_patterns() -> dict[str, re.Pattern[str]]:
    """Every compiled pattern a physics module keeps at module level."""
    found: dict[tuple[str, int], tuple[str, re.Pattern[str]]] = {}
    for info in pkgutil.walk_packages(physics_package.__path__, f"{physics_package.__name__}."):
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            candidates = value if isinstance(value, tuple | list) else (value,)
            for index, candidate in enumerate(candidates):
                if isinstance(candidate, re.Pattern):
                    label = f"{info.name}.{name}[{index}]"
                    found.setdefault((candidate.pattern, candidate.flags), (label, candidate))
    return dict(found.values())


def _elapsed(action: object, text: str) -> float:
    assert callable(action)
    start = time.perf_counter()
    action(text)
    return time.perf_counter() - start


def _clear_caches() -> None:
    extract.needs_physics.cache_clear()
    extract._extract_physics_intent.cache_clear()


def test_every_physics_pattern_is_linear_on_adversarial_text() -> None:
    patterns = _physics_patterns()
    assert len(patterns) > 100, "the scan should see the extractor and cue tables"
    slow = []
    for text_name in _NAMES:
        text = _text(text_name, 8_000)
        for label, pattern in patterns.items():
            elapsed = _elapsed(pattern.search, text)
            if elapsed > _PATTERN_BUDGET_SECONDS:
                slow.append(f"{label} on {text_name}: {elapsed:.2f}s")
    assert not slow, "quadratic physics patterns:\n" + "\n".join(slow)


@pytest.mark.wall_clock
@pytest.mark.parametrize("name", _NAMES)
def test_detection_cost_does_not_grow_with_the_paste(name: str) -> None:
    _clear_caches()
    elapsed = _elapsed(extract.needs_physics, _text(name, _MAX_SUBJECT_TEXT))
    assert elapsed < _CALL_BUDGET_SECONDS, f"{name}: {elapsed:.2f}s"


@pytest.mark.wall_clock
@pytest.mark.parametrize("name", _NAMES)
def test_extraction_at_its_cap_stays_cheap(name: str) -> None:
    _clear_caches()
    elapsed = _elapsed(extract.extract_physics_intent, _text(name, _MAX_PHYSICS_REQUEST))
    assert elapsed < _CALL_BUDGET_SECONDS, f"{name}: {elapsed:.2f}s"


@pytest.mark.wall_clock
def test_a_pasted_report_is_not_physics_and_does_not_stall() -> None:
    report = _repeat(_REPORT, 3_000)
    _clear_caches()
    assert _elapsed(extract.needs_physics, report) < _CALL_BUDGET_SECONDS
    assert extract.needs_physics(report) is False


def test_detection_and_extraction_run_once_per_text(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"cue": 0, "prepare": 0}
    real_cue = extract.has_supported_physics_cue

    def counting_cue(cleaned: str) -> bool:
        calls["cue"] += 1
        return real_cue(cleaned)

    from app.modules.physics import request

    real_prepare = request.prepare_physics_request

    def counting_prepare(cleaned: str) -> request.PhysicsRequest:
        calls["prepare"] += 1
        return real_prepare(cleaned)

    monkeypatch.setattr(extract, "has_supported_physics_cue", counting_cue)
    monkeypatch.setattr(request, "prepare_physics_request", counting_prepare)
    _clear_caches()
    text = "A ball is dropped from a height of 20 m. Find the time to ground. Use g=10."
    for _ in range(5):
        assert extract.needs_physics(text)
        assert extract.extract_physics_intent(text) is not None
    assert calls == {"cue": 1, "prepare": 1}


def test_each_caller_gets_its_own_intent() -> None:
    text = "A ball is dropped from a height of 20 m. Find the time to ground. Use g=10."
    first = extract.extract_physics_intent(text)
    assert first is not None and first.physics_params is not None
    first.physics_params["h0"] = 999.0
    second = extract.extract_physics_intent(text)
    assert second is not None and second.physics_params is not None
    assert second.physics_params["h0"] == 20


@pytest.mark.wall_clock
@pytest.mark.parametrize("run", [",", ", ", ". ", " = "])
def test_punctuation_between_a_label_and_its_value_stays_linear(run: str) -> None:
    # Each comma once doubled the label-gap fullmatch: 40 would have taken days.
    text = "What is the net force on a body of mass" + run * 40 + "x 5 kg at 2 m/s^2?"
    _clear_caches()
    assert _elapsed(extract.extract_physics_intent, text) < _CALL_BUDGET_SECONDS
    start = time.perf_counter()
    find_value_with_specific_unit(text, "kg", ("mass",))
    assert time.perf_counter() - start < _PATTERN_BUDGET_SECONDS


def test_a_long_resistor_list_still_declines() -> None:
    assert resistor_values("three resistors of 2, 3 and 6 ohms in parallel") == [2.0, 3.0, 6.0]
    # More than the network limit: enough values come back to refuse it.
    assert len(resistor_values("1, 2, 3, 4, 5, 6, 7 ohms in series")) > 4


@pytest.mark.parametrize(
    ("text", "keywords", "expected"),
    [
        ("a 2 kg cart pushes a 5 kg block", ("block",), (5.0, "kg")),
        ("a 2 kg cart pushes a 5 kg block", ("cart",), (2.0, "kg")),
        # The word names the number that follows it.
        ("3 kg mass 4 kg", ("mass",), (4.0, "kg")),
        # Equidistant, and neither side is a label: the first one written wins.
        ("3 kg x mass x 4 kg", ("mass",), (3.0, "kg")),
        # A keyword that overlaps the value is distance zero.
        ("the 7 kg-block and a 9 kg ball", ("kg-block",), (7.0, "kg")),
        ("no keyword here, 6 kg then 8 kg", ("crate",), (6.0, "kg")),
    ],
)
def test_nearest_keyword_value(
    text: str, keywords: tuple[str, ...], expected: tuple[float, str]
) -> None:
    assert find_value_with_specific_unit(text, "kg", keywords) == expected


@pytest.mark.parametrize(
    ("a", "b", "c", "expected"),
    [
        (1, -3, 2, (1.0, 2.0)),
        (-4.905, 0, 20, (-2.019275, 2.019275)),
        (1, 2, 1, (-1.0,)),
        (1, 0, 1, ()),
        (0, 5, -10, (2.0,)),
        (0, 0, 3, ()),
        (2, 0, 0, (0.0,)),
        # Cancellation-prone: b² dwarfs 4ac, and the small root must survive.
        (1, 1e8, 1, (-1e8, -1e-8)),
    ],
)
def test_quadratic_roots(a: float, b: float, c: float, expected: tuple[float, ...]) -> None:
    roots = quadratic_roots(a, b, c)
    assert len(roots) == len(expected)
    for root, want in zip(roots, expected, strict=True):
        assert root == pytest.approx(want, rel=1e-6, abs=1e-12)
