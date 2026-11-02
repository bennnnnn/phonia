"""The chemistry corpus: no verified answer is wrong, and coverage only grows."""

from __future__ import annotations

import re

import pytest

from app.core.config import Settings
from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.sig_figs import decimals_of
from app.modules.physics import build_verified_physics_block, extract_physics_intent
from app.services.subjects.dispatch import detect_subject
from app.tests.modules.chemistry.corpus import (
    ANSWERABLE,
    COVERAGE_FLOOR,
    MUST_DECLINE,
    NOT_CHEMISTRY,
    Case,
)

_NUMBER = r"(?<![\w.])(-?\d+(?:\.\d+)?)(?:\s*×\s*10\^(-?\d+))?"
# A worked value and a table-rounded one may differ past the shown figures by this much.
_SLACK = 1e-4


_SETTINGS = Settings(math_tools_enabled=True)


def _answer(question: str) -> str | None:
    """The verified answer of the subject the question routes to, or None when it declines.

    A gas law, Q = mcΔT or a half-life is physics' law (one implementation), answered in a
    chemistry question's own units: 49.2 L, not 0.0492 m³.
    """
    subject = detect_subject(question)
    if subject == "physics":
        physics = extract_physics_intent(question)
        verified = None if physics is None else build_verified_physics_block(physics, _SETTINGS)
        return None if verified is None else verified.canonical_answer
    if subject != "chemistry":
        return None
    intent = extract_chemistry_intent(question)
    block = None if intent is None else build_verified_chemistry(intent)
    return None if block is None else block.canonical_answer


_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def _plain(answer: str) -> str:
    """Physics writes ``10⁻⁴``; chemistry writes ``10^-4``. Read both as the latter."""
    text = answer.replace("−", "-")
    return re.sub(
        r"10([⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "10^" + m.group(1).translate(_SUPERSCRIPT), text
    )


def _shown(case: Case, answer: str) -> tuple[float, float] | None:
    """The value the answer shows for ``case`` and half a unit in its last place."""
    if case.label:
        pattern = rf"{re.escape(case.label)}\s*=\s*{_NUMBER}"
    elif case.unit:
        pattern = rf"{_NUMBER}\s*{re.escape(case.unit)}(?![\w/])"
    else:
        pattern = rf"=\s*{_NUMBER}"
    match = re.search(pattern, _plain(answer))
    if match is None:
        return None
    mantissa, exponent = match.group(1), int(match.group(2) or 0)
    return float(mantissa) * 10**exponent, 0.5 * 10 ** (exponent - decimals_of(mantissa))


def _agrees(case: Case, answer: str) -> bool:
    if case.text and case.text not in answer:
        return False
    if case.value is None:
        return True
    shown = _shown(case, answer)
    if shown is None:
        return False
    value, half_place = shown
    return abs(value - case.value) <= half_place + _SLACK * abs(case.value)


@pytest.mark.parametrize("case", ANSWERABLE, ids=[case.question[:60] for case in ANSWERABLE])
def test_a_verified_answer_is_never_wrong(case: Case) -> None:
    answer = _answer(case.question)
    if answer is not None:
        assert _agrees(case, answer), f"verified {answer!r}, expected {case}"


@pytest.mark.parametrize("question", MUST_DECLINE)
def test_an_ambiguous_question_declines(question: str) -> None:
    assert _answer(question) is None


@pytest.mark.parametrize("text", NOT_CHEMISTRY)
def test_ordinary_text_is_not_chemistry(text: str) -> None:
    assert is_chemistry_question(text) is False


def test_coverage_never_drops() -> None:
    answered = [case for case in ANSWERABLE if _answer(case.question) is not None]
    print(f"chemistry corpus coverage: {len(answered)}/{len(ANSWERABLE)}")
    assert len(answered) >= COVERAGE_FLOOR


@pytest.mark.parametrize(
    ("case", "answer", "agrees"),
    [
        (Case("pH", 2.875, label="pH"), "pH = 2.88", True),
        (Case("pH", 2.875, label="pH"), "pH = 2.87", True),
        (Case("pH", 2.875, label="pH"), "pH = 2.86", False),
        (Case("V", 22.414, "L"), "V = 22 L", True),
        (Case("V", 22.414, "L"), "V = 22.7 L", False),
        (Case("Ksp", 1.342e-5, "mol/L"), "s = 1.3 × 10^-5 mol/L", True),
        (Case("Ksp", 1.342e-5, "mol/L"), "s = 1.4 × 10^-5 mol/L", False),
        (Case("c", 0.25, "mol/L"), "c = 0.25 mol/kg", False),
        (Case("lim", 72.06, "g", text="= O2"), "Limiting reagent = O2; 72.06 g H2O", True),
        (Case("lim", 72.06, "g", text="= O2"), "Limiting reagent = H2; 72.06 g H2O", False),
    ],
)
def test_agreement_is_judged_to_the_figures_shown(case: Case, answer: str, agrees: bool) -> None:
    assert _agrees(case, answer) is agrees
