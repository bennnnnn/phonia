"""One owner decides which STEM subject a line is (code-health audit DUP-05).

Presentation, routing, related questions and the maths follow-up gate each asked their
own gates in their own order: "h = 20t - 5t^2, find the maximum height" was solved by
maths and prompted with physics' pack, and a balanced equation went to the maths lane.
Each now asks ``detect_subject``; this holds them to it across every corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import model_catalog
from app.modules.chat.continuation_subject import (
    blocks_math_followup,
    classify_presentation_subject,
)
from app.modules.chat.follow_up_thread import subject_for_related
from app.modules.chat.model_routing.route import route_chat_model
from app.services.subjects.dispatch import detect_subject
from app.services.text_normalize import collapse_ws
from app.tests.behavior.cases import CASES

_BEHAVIOR = Path(__file__).parents[1] / "behavior"


def _corpus() -> list[str]:
    """Every battery, sweep and STEM prompt, once."""
    lines = [case.prompt for case in CASES]
    for folder in ("stem_corpus/*", "sweep_corpus"):
        for path in sorted(_BEHAVIOR.glob(f"{folder}/*.json")):
            lines += [row["prompt"] for row in json.loads(path.read_text())]
    return list(dict.fromkeys(line for line in lines if line.strip()))


@pytest.mark.parametrize(
    ("line", "subject"),
    [
        # Cues physics, but states the function and asks its maximum: calculus answers it.
        ("a ball's height is h = 20t - 5t^2, find the maximum height", "math"),
        # Masses physics would read; chemistry closes it first.
        ("What is the mass percent of 5 g of sugar in 95 g of water?", "chemistry"),
        ("Balance H2 + O2 -> H2O", "chemistry"),
        ("A 2 kg ball falls 5 m. Find its speed.", "physics"),
    ],
)
def test_named_lines_have_one_subject(line: str, subject: str) -> None:
    assert detect_subject(line) == subject
    assert classify_presentation_subject(line) == subject
    assert subject_for_related(line) == subject
    assert blocks_math_followup(line) == (subject != "math")
    on_math_lane = route_chat_model(line) == model_catalog.auto_math_alias()
    assert on_math_lane == (subject == "math")


def test_a_genotype_cross_is_biology_not_a_drawn_square() -> None:
    line = "Draw a flowchart of a Punnett square cross for Aa x Aa with 4 offspring"
    assert detect_subject(line) is None
    assert classify_presentation_subject(line) == "biology"


def test_every_reader_agrees_with_detect_subject() -> None:
    math_lane = model_catalog.auto_math_alias()
    disagree: list[str] = []
    for line in _corpus():
        subject = detect_subject(line)
        if subject is not None and classify_presentation_subject(line) != subject:
            disagree.append(f"presentation: {line}")
        if blocks_math_followup(line) != (subject in {"physics", "chemistry"}):
            disagree.append(f"follow-up gate: {line}")
        collapsed = detect_subject(collapse_ws(line))
        if collapsed is not None and subject_for_related(line) != collapsed:
            disagree.append(f"related: {line}")
        if subject != "math" and route_chat_model(line) == math_lane:
            disagree.append(f"maths lane: {line}")
    assert not disagree, "\n".join(disagree[:20])
