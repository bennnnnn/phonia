"""A verified card only from a question the readers read whole (2026-11-01 baseline).

The subject readers are English grammars that read numbers the English way. "Deux
résistances de 10 ohms sont en parallèle sous 5 V, courant total ?" got a checked 0.5 A for
one resistor ("deux" unread; two in parallel draw 1 A), and "1.200 + 800" from a Spanish user
a checked 801.2 (1.200 is 1200 there). A question in another language, or with a number its
writer's locale reads otherwise, keeps no verified result: no card, no picture, no instant
reply. An English question keeps its card, names and symbols included.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.chat.prompt_builder import SubjectFetch
from app.modules.chat.tool_loop.calls import _tool_call_matches_user
from app.modules.chat.tool_verified import with_tool_verified
from app.modules.chat.turn_prep import augment
from app.modules.chat.turn_prep.followups import SubjectFollowup
from app.modules.chat.whole_question import answers_with, whole_question_fetch
from app.modules.turn_reading.readable import misread_number, other_language, unreadable
from app.services.solving import VerifiedSolveBlock

_DROPPED = SubjectFetch(None, None, False, None, None)


@pytest.mark.parametrize(
    "question",
    [
        "Deux résistances de 10 ohms sont en parallèle sous 5 V, courant total ?",
        # A word after a number is a unit only when it is short and English could write it.
        "2 résistances de 10 ohms, 5 V",
        "Dos resistencias de 10 ohmios están en paralelo a 5 V, ¿cuál es la corriente total?",
        "Berechne die Geschwindigkeit eines Autos, das in 5 s 100 m fährt.",
        "Calcola la velocità di un'auto che percorre 100 m in 5 s.",
        "Calcule a velocidade de um carro que percorre 100 m em 5 s.",
        "5 saniyede 100 m giden bir arabanın hızı nedir?",
        "2 A ን በ15 Ω ተከላካይ ውስጥ ለማስገደድ ምን ያህል ቮልቴጅ ያስፈልጋል?",
        "Какое напряжение нужно, чтобы через резистор 15 Ω шёл ток 2 A?",
        "pOH 3.2 है, pH ज्ञात कीजिए।",
        # One word of another language and none of English.
        "résous 3x + 7 = 22",
        "resuelve 2x + 3 = 7",
        "si x = 2, halla 3x + 1",
    ],
)
def test_a_question_in_another_language_is_read_as_one(question: str) -> None:
    assert other_language(question)
    assert unreadable(question, "en") == "other_language"


@pytest.mark.parametrize(
    "question",
    [
        "What is the de Broglie wavelength of an electron moving at 2 x 10^6 m/s?",
        "de Broglie wavelength of a 145 g baseball thrown at 40 m/s",
        "explain le chatelier's principle",
        "Use the van der Waals equation for 1 mol of CO2 at 300 K in 0.5 L",
        "Use L'Hôpital's rule to find the limit of sin(x)/x as x approaches 0",
        "José pushes a 20 kg box with a net force of 50 N. what is its acceleration?",
        "a 5 µF capacitor is charged to 12 V. how much energy does it store?",
        "Light enters glass at θ = 30°; n = 1.5. Find the angle of refraction.",
        "angles of 30º and 60º in a triangle, find the third",
        "Secants CA and CE intersect a circle at A, B, D and E. DA bisects ∠CAB.",
        "the meeting is at 3pm EST, what time is that in addis?",
        "What is the atomic number of La, Es and Os?",
        "I've got 2x + 3 = 7, can you solve it?",
        "solve log2(x) + log2(x-2) = 3",
        "The mean of six numbers is 12. Find the sixth number.",
        # Units after a number, or in mixed case, are no words: "um" is not Portuguese.
        "5 nA in A",
        "12 um in m",
        "5.2 au in km",
        "current 5 nA through 2 MΩ resistor voltage",
        # One word with a letter English does not write is a loanword or a name.
        "5 ångström in m",
        "convert 500 nm to um",
        "Earth–Sun distance in au",
        "wavelength 500 nm in um",
        "ampère's law 5 A at 2 cm",
        "schrödinger equation for a particle in a 1 nm box",
        "schrödinger equation for n = 2",
        "poincaré",
        "the poincaré recurrence time for 3 particles",
        # Name particles alone are names.
        "de Broglie et al. wavelength electron 1e6 m/s",
        # No words: no language.
        "1.200 + 800",
        "x+y+z=6, 2x-y+z=3, x+2y-z=2",
        "$\\int_{0}^{2} x^3\\,dx$",
    ],
)
def test_an_english_question_is_not_another_language(question: str) -> None:
    assert not other_language(question)


@pytest.mark.parametrize(
    ("question", "locale", "misread"),
    [
        # A dot groups thousands in Spanish, German, Italian, Portuguese and Turkish.
        ("1.200 + 800", "es", True),
        ("a 1.500 kg car", "de", True),
        ("media de 1.200, 1.500 y 1.800", "es", True),
        ("2.718^2", "it", True),
        ("1.200 + 800", "en", False),
        ("1.200 + 800", "fr", False),
        ("0.125 + 1", "es", False),
        ("3.14159 * 2", "es", False),
        ("2.5 + 1.25", "pt", False),
        # A comma is the decimal mark there and in French and Russian.
        ("1,200 + 800", "fr", True),
        ("1,200 + 800", "ru", True),
        ("1,200 + 800", "en", False),
        ("1,200 + 800", "am", False),
        ("x+y+z=6, 2x-y+z=3", "fr", False),
        # Groups set apart by a space are read as two numbers, whoever writes them; three
        # digits in a row are a list.
        ("a car of mass 1 200 kg", "en", True),
        ("12 000 + 800", "en", True),
        ("100 000 + 5", "en", True),
        ("mean of 120 135 150", "en", False),
        ("The Moon is 384 400 km away", "en", True),
        ("light at 299 792 458 m/s", "en", True),
        ("mean of 120 135 150 and 160", "en", False),
        ("find the variance of 100 200 300", "en", False),
        ("lcm 120 150", "en", False),
        ("my phone number is 555 123 4567", "en", False),
        ("1 200 + 800", "fr", True),
        ("3 + 4", "en", False),
        ("x^2 + 4 = 100", "en", False),
        ("```\n1 200\n```", "en", False),
    ],
)
def test_a_number_the_writer_reads_otherwise(question: str, locale: str, misread: bool) -> None:
    assert misread_number(question, locale) is misread


def _fetched(answer: str = "0.5\\,\\mathrm{A}", *, direct: str | None = None) -> SubjectFetch:
    verified = VerifiedSolveBlock(text="block", subject="physics", display_answer=answer)
    return SubjectFetch("block", verified, False, None, direct)


def test_a_question_in_another_language_loses_its_verified_result() -> None:
    question = "Deux résistances de 10 ohms sont en parallèle sous 5 V, courant total ?"
    assert whole_question_fetch(question, _fetched()) == _DROPPED


def test_a_number_the_locale_reads_otherwise_loses_its_verified_result() -> None:
    fetched = _fetched("801.2")
    assert whole_question_fetch("1.200 + 800", fetched, locale="es") == _DROPPED
    assert whole_question_fetch("1.200 + 800", fetched, locale="en") == fetched


def test_an_english_question_keeps_its_verified_result() -> None:
    fetched = _fetched("30\\,\\mathrm{V}")
    question = "What voltage drives 2 A through a 15 Ω resistor?"
    assert whole_question_fetch(question, fetched, locale="fr") == fetched


def test_a_picture_without_a_card_goes_too() -> None:
    """The circuit drawn for the French question showed one resistor."""
    picture = VerifiedSolveBlock(text="block", subject="physics")
    question = "Deux résistances de 10 ohms sont en parallèle sous 5 V, courant total ?"
    assert not answers_with(question, picture)
    assert answers_with("Draw two 10 Ω resistors in parallel across 5 V", picture)


def test_a_reply_written_whole_by_the_solvers_goes_too() -> None:
    """A reply both halves of "…, and also …" wrote themselves goes when one is unread."""
    fetched = SubjectFetch(None, None, False, None, "801.2\n\n---\n\nx = 2")
    question = "1.200 + 800, and also solve 2x = 4"
    assert whole_question_fetch(question, fetched, locale="es") == _DROPPED
    assert whole_question_fetch(question, fetched, locale="en") == fetched


def test_a_follow_up_to_an_unread_question_gets_no_card() -> None:
    """The follow-up is English; the problem it solves again is the French line before it."""
    problem = "Deux résistances de 10 ohms sont en parallèle sous 5 V, courant total ?"
    fetched = _fetched()
    assert whole_question_fetch("how?", fetched, problems=(None, None, problem)) == _DROPPED
    assert whole_question_fetch("how?", fetched, problems=(None, None, None)) == fetched


def test_the_tool_loop_gives_an_unread_question_no_card() -> None:
    tool = VerifiedSolveBlock(text="tool", subject="math", canonical_answer="801.2")
    assert with_tool_verified(None, tool, "1.200 + 800", "es") is None
    assert with_tool_verified(None, tool, "1.200 + 800", "en") is tool


def _turn(content: str, earlier: str, locale: str) -> tuple[Any, Any, list[dict[str, str]]]:
    request = SimpleNamespace(content=content)
    identity = SimpleNamespace(user=SimpleNamespace(locale=locale))
    prompt = [
        {"role": "user", "content": earlier},
        {"role": "assistant", "content": "Here it is."},
        {"role": "user", "content": content},
    ]
    return request, identity, prompt


@pytest.mark.parametrize(
    ("content", "earlier"), [("graph it", "y = 1.200x + 3"), ("5", "3x + 1.200 = y")]
)
def test_a_follow_up_that_borrows_an_unread_line_gets_no_card(content: str, earlier: str) -> None:
    """A Spanish user's "graph it" plots the last plottable line, and "5" continues the open
    equation: 1.200 was 1200 there, and the graph drew 1.2x + 3."""
    fetched = _fetched("1.2 x + 3")
    request, identity, prompt = _turn(content, earlier, "es")
    got = augment._readable_fetch(request, identity, prompt, SubjectFollowup(), fetched)
    assert got == _DROPPED
    request, identity, prompt = _turn(content, earlier, "en")
    assert augment._readable_fetch(request, identity, prompt, SubjectFollowup(), fetched) == fetched


@pytest.mark.asyncio
async def test_the_tool_matches_no_unread_earlier_line(thread_sympy_executor: None) -> None:
    """The tool's call is matched against the newest line with a formula: after "check it
    with sympy", the Spanish user's 1.200 + 800 before it."""
    args = {"action": "simplify", "expr": "1.200 + 800"}
    texts = ["check it with sympy please", "1.200 + 800"]
    assert not await _tool_call_matches_user(args, texts, Settings(), "es")
    assert await _tool_call_matches_user(args, texts, Settings(), "en")
