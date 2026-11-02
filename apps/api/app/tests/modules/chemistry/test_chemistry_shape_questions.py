"""A molecule's shape asked in words is read whole and drawn, or declines.

Live failure (2026-10-25), the student's lines in order: "Why is water bent tho, co2 isnt" got
no verified answer; "Can u show me both" went to a photo search for "both"; "lol no the
molecules" got ASCII art in a code box and a broken CO2 drawing.
"""

from __future__ import annotations

import json
import re

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.direct import format_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.extractors.shapes import shape_question
from app.modules.chemistry.fence import validate_chemistry_fences
from app.modules.chemistry.followup import chemistry_followup_problem
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.schemas import ChemistryIntent
from app.modules.chemistry.shape_followup import is_show_line
from app.modules.chemistry.solvers import solve_chemistry
from app.services.solving import SolveServiceError
from app.services.subjects.dispatch import detect_subject

_LIVE = (
    "Ok so chem hw. how much water do i get if i burn like 4g of h2",
    "Wait so its 4.5 or 36?? I'm confused",
    "Ok and the o2 how much of that",
    "Why is water bent tho, co2 isnt",
)
_SCENE = re.compile(r"```chem_scene\n(.*?)\n```", re.DOTALL)


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    verified = None if intent is None else build_verified_chemistry(intent)
    return None if verified is None else verified.result.answer


def _recent(*lines: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for line in lines:
        turns.extend((("user", line), ("assistant", "Here it is.")))
    return turns


@pytest.mark.parametrize(
    ("question", "molecules", "answer"),
    [
        ("Why is water bent tho, co2 isnt", ("H2O", "CO2"), "H2O: bent, 104.5°, polar"),
        ("why is water bent but co2 linear", ("H2O", "CO2"), "CO2: linear, 180°, nonpolar"),
        ("compare the shapes of h2o and co2", ("H2O", "CO2"), "H2O: bent"),
        ("what are the shapes of CH4 and NH3", ("CH4", "NH3"), "NH3: trigonal pyramidal, 107°"),
        ("why is water bent", ("H2O",), "geometry: bent, 104.5°"),
        ("what is the shape of water", ("H2O",), "geometry: bent"),
        ("shape of h2o", ("H2O",), "geometry: bent"),
        ("shape of a water molecule", ("H2O",), "geometry: bent"),
        ("what is the shape of a water molecule", ("H2O",), "geometry: bent"),
        ("what shape is ch4", ("CH4",), "geometry: tetrahedral, 109.5°"),
        ("is co2 linear", ("CO2",), "geometry: linear, 180°"),
        ("why is co2 linear", ("CO2",), "geometry: linear"),
        ("molecular geometry of ammonia", ("NH3",), "geometry: trigonal pyramidal, 107°"),
        ("bond angle in water", ("H2O",), "104.5°"),
        ("bond angle in h2o", ("H2O",), "104.5°"),
        ("is nh3 polar", ("NH3",), "polarity: polar"),
        ("is co2 polar or nonpolar", ("CO2",), "polarity: nonpolar"),
        ("how come water is bent", ("H2O",), "geometry: bent"),
        ("what is the polarity of water", ("H2O",), "polarity: polar"),
        ("co2 shape", ("CO2",), "geometry: linear"),
        ("what are the shapes of water and co2", ("H2O", "CO2"), "H2O: bent"),
        # Beryllium, aluminium and tin(II) chloride are molecules; only salts decline.
        ("is BeCl2 linear", ("BeCl2",), "geometry: linear, 180°"),
        ("is BeF2 linear", ("BeF2",), "geometry: linear, 180°"),
        ("what shape is CH2O", ("CH2O",), "trigonal planar, 120°"),
        ("is h2o polar", ("H2O",), "polarity: polar"),
        ("what shape is AlCl3", ("AlCl3",), "trigonal planar"),
        ("is CH2Cl2 polar", ("CH2Cl2",), "polarity: polar"),
        ("is XeOF4 polar", ("XeOF4",), "polarity: polar"),
        ("Ok so chem hw. why is water bent", ("H2O",), "geometry: bent"),
        ("what is the molecular geometry of BF3", ("BF3",), "trigonal planar, 120°"),
        # A false premise is answered with the verified shape, not agreed with.
        ("why is co2 bent", ("CO2",), "geometry: linear, 180°"),
    ],
)
def test_a_shape_question_in_words_is_verified(
    question: str, molecules: tuple[str, ...], answer: str
) -> None:
    assert shape_question(question) == molecules
    assert is_chemistry_question(question)
    assert detect_subject(question) == "chemistry"
    assert answer in (_answer(question) or "")


@pytest.mark.parametrize(
    "text",
    [
        "what shape is the earth",
        "the pipe is bent",
        "bent over backwards for my boss",
        "my phone is bent",
        "co2 levels are rising",
        "is co2 bad",
        "is co2 bad for the planet",
        "shape of my nose",
        "what shape is a stop sign",
        "what is the bond angle in a bond portfolio",
        "why is the tower of pisa bent",
        "why is the tower of pisa leaning",
        "why is my back bent",
        "is water wet",
        "why is water blue",
        # No central atom, or more than one: not read as VSEPR.
        "what shape is oxygen",
        "shape of ethanol",
        "is iron linear",
        "what shape is lead",
        # A clause the grammar does not know.
        "why is co2 nonpolar if it has polar bonds",
        # The 2017 film: a word-named substance in a bare noun phrase, or a title.
        "The Shape of Water",
        "the shape of water",
        "Shape of Water?",
        "ok so the shape of water",
        "what is The Shape of Water",
        "is the shape of water a good movie",
        "who directed the shape of water",
        "geometry of ammonia",
        "polarity of water",
        "water shape",
        "the shapes of water and co2",
    ],
)
def test_shapes_in_everyday_words_are_not_a_vsepr_question(text: str) -> None:
    assert shape_question(text) is None
    assert extract_chemistry_intent(text) is None
    assert not is_chemistry_question(text)


@pytest.mark.parametrize(
    "question",
    [
        # Salts are ionic lattices, not linear molecules (review, 2026-10-25).
        "is calcium chloride polar",
        "what shape is CaCl2",
        "shape of CaCl2",
        "is MgCl2 linear",
        "what shape is BaCl2",
        "what shape is CaF2",
        "shape of magnesium chloride",
        "shape of strontium chloride",
        "is calcium fluoride linear",
        "what shape is AlF3",
        # Network solids: no O=Si=O molecule.
        "what shape is SiO2",
        "shape of SiO2",
        "is SnO2 linear",
        # Polarity that depends on where unlike atoms sit.
        "is PCl3F2 polar",
        "is SF4Cl2 polar",
        "is XeF2Cl2 polar",
        "shape of PCl2F3",
        # An oxoacid's H sits on O (H-O-N=O): bent at N, not trigonal planar.
        "what shape is nitrous acid",
        "is hno2 polar",
        "what shape is HNO2",
        "shape of HIO3",
        # A charge written apart is an ion this reader cannot see: sulfite is pyramidal.
        "shape of SO3 2-",
        "what shape is so3 2-",
        "is SO3 2- polar",
        "why is water bent tho, so3 2- isnt",
        "shape of SO3(2-)",
        "shape of SO3 (2-)",
        "shape of SO3 ion",
    ],
)
def test_a_shape_no_single_answer_fits_declines(question: str) -> None:
    assert _answer(question) is None


def test_geometry_homework_stays_maths() -> None:
    text = "geometry homework: find the angle of a triangle with sides 3 4 5"
    assert shape_question(text) is None
    assert detect_subject(text) == "math"


def test_two_molecules_draw_two_pictures() -> None:
    intent = extract_chemistry_intent("Why is water bent tho, co2 isnt")
    assert intent is not None and (intent.chemistry_op, intent.formula) == ("vsepr", "H2O, CO2")
    verified = build_verified_chemistry(intent)
    assert verified is not None
    reply = format_direct_chemistry_reply(verified)
    scenes = [json.loads(body) for body in _SCENE.findall(reply)]
    assert [(scene["title"], scene["geometry"]) for scene in scenes] == [
        ("H₂O", "bent"),
        ("CO₂", "linear"),
    ]
    # The model's own drawings are dropped at finalize and the server's two kept.
    finalized = validate_chemistry_fences(
        "Water is bent.\n\n```chem_scene\n{}\n```\n```\nO=C=O\n```", verified
    )
    assert len(_SCENE.findall(finalized)) == 2


@pytest.mark.parametrize("formula", ["H2O, H2O", "H2O, O2", "H2O, CO2, CH4"])
def test_a_comparison_needs_two_different_molecules_with_a_center(formula: str) -> None:
    intent = ChemistryIntent(kind="structure", chemistry_op="vsepr", formula=formula)
    with pytest.raises(SolveServiceError):
        solve_chemistry(intent)


@pytest.mark.parametrize(
    ("lines", "line"),
    [
        (_LIVE, "Can u show me both"),
        ((*_LIVE, "Can u show me both"), "lol no the molecules"),
        (("why is water bent",), "show me the molecules"),
        (("why is water bent",), "display them"),
        (("why is water bent",), "show me it"),
        (("why is water bent",), "show me"),
        (("why is water bent",), "what do they look like"),
        (("why is water bent",), "can you show me both molecules pls"),
        ((*_LIVE, "Can u show me both"), "show me both of them"),
        (_LIVE, "show me what they look like"),
        (_LIVE, "show me each of them"),
        (_LIVE, "show me the shapes"),
        (_LIVE, "show me the models"),
        (_LIVE, "show us both"),
        (_LIVE, "show me both then"),
        (_LIVE, "show me the drawings"),
    ],
)
def test_a_line_that_asks_to_see_them_draws_the_shape_question_again(
    lines: tuple[str, ...], line: str
) -> None:
    problem = chemistry_followup_problem(line, _recent(*lines))
    assert problem is not None
    assert shape_question(problem) is not None


@pytest.mark.parametrize(
    ("lines", "line"),
    [
        (("what's the difference between a crocodile and an alligator",), "show me both"),
        (("graph y = x^2 and y = 2x",), "draw them"),
        # Another line in between: the shape question is no longer the one being looked at.
        (("why is water bent", "what is the capital of france"), "show me both"),
        (("why is water bent",), "show me both crocodiles"),
        (("why is water bent",), "draw a cat"),
        (_LIVE, "show me a photo of both"),
        (_LIVE, "show me a picture of the real ones"),
        (_LIVE, "show me a waterfall"),
        (_LIVE, "ok i see"),
        # Draw verbs are image generation's: the composer sends them before a chat turn.
        (_LIVE, "draw both"),
        (_LIVE, "draw both of them"),
        (("why is water bent",), "draw them"),
        (("why is water bent",), "sketch them"),
        (_LIVE, "draw me a picture"),
    ],
)
def test_a_show_line_after_anything_else_is_not_chemistrys(
    lines: tuple[str, ...], line: str
) -> None:
    assert chemistry_followup_problem(line, _recent(*lines)) is None


@pytest.mark.parametrize(
    ("line", "shows"),
    [
        ("Can u show me both", True),
        ("lol no the molecules", True),
        ("show me the shapes please", True),
        ("let me see them", True),
        ("what do they look like", True),
        ("show me both crocodiles", False),
        ("show me the steps", False),
        ("draw a cat", False),
        ("no thanks", False),
        ("show me both of them", True),
        ("show me what they look like", True),
        ("show us both", True),
        ("draw both of them", False),
        ("draw both", False),
        ("sketch them", False),
        ("draw me a picture", False),
        ("display them", True),
        ("can i see them", True),
        ("show me a photo of both", False),
        ("show me an image of both", False),
        ("show me the real ones", False),
        ("show me how", False),
        ("ok i see", False),
        ("i see them", False),
        ("show me her", False),
    ],
)
def test_the_show_grammar_reads_the_whole_line(line: str, shows: bool) -> None:
    assert is_show_line(line) is shows
