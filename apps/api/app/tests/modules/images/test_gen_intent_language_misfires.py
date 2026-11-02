"""Every misfire the eight reviews found, and the round-5 to round-8 probes: answered.

A misfire (a picture drawn where the user wanted words) costs a daily picture and the
answer. ``language_misfires.json`` holds each sentence a review named as drawn wrongly
(physics homework, plans, tables, algorithms, idioms, "Dibuja un ejemplo", "Mal den
Teufel nicht an die Wand", a Docker image…), the reviewers' non-picture probe lines,
the everyday lines with picture words written for round 5, most of them in a draw-me
shape ("Dibújame la pirámide alimenticia", "Zeichne mir einen Trainingsplan"), review 5's
task subjects ("Dibújame un cuadro comparativo", "Нарисуй мне сказку на ночь"), round
6's blind set and its drawable heads with task words ("un volcán con sus partes"), review
6's listed nouns beside a format, a data structure or a second request ("un gato en
ASCII", "un árbol binario", "un perro y sugiéreme nombres"), round 7's blind set, and
review 7's and round 8's draw-me lines the user asks about rather than asks for: translated
("Traduce al inglés: dibújame un gato"), checked ("¿Esta frase es correcta? Dibújame un
gato"), explained, quoted or attributed ("«Dibújame un cordero»: ¿quién lo dijo?"), and
review 8's: asked about with a dropped "it" ("Dime si es educado. Dibújame un gato") or
in English ("Dibújame un gato. Why is the me at the end?"). No rule told those apart
from a real second request, so no other-language message is cut into a picture and a
request at all.

Every line is checked here, at the reader. The behavior sweep runs every tenth line of each
group through the whole turn (``sweep_corpus/picture_languages.json``), so a rule elsewhere
that hijacks one of these shapes shows up there without repeating 2,400 full turns in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.chat.turn_prep.intents import plan_turn
from app.modules.images.intent import composer_image_intent

_GROUPS: dict[str, list[str]] = json.loads(
    Path(__file__).with_name("language_misfires.json").read_text(encoding="utf-8")
)


def test_every_review_is_here() -> None:
    reviews = {group.split(" (")[0] for group in _GROUPS}
    assert {f"review {n}" for n in range(1, 9)} <= reviews
    assert sum(len(texts) for texts in _GROUPS.values()) >= 2400


def test_the_sweep_runs_every_group_through_the_whole_turn() -> None:
    corpus = Path(__file__).parents[2] / "behavior" / "sweep_corpus" / "picture_languages.json"
    swept = {entry["prompt"] for entry in json.loads(corpus.read_text(encoding="utf-8"))}
    assert [name for name, texts in _GROUPS.items() if not swept & set(texts)] == []


# One test per group, not per line: 2,400 parametrized tests cost CI four times the checks.
@pytest.mark.parametrize(
    "group", [pytest.param(name, id=f"group{n}") for n, name in enumerate(_GROUPS)]
)
def test_no_picture(group: str) -> None:
    drawn = [
        text
        for text in _GROUPS[group]
        if composer_image_intent(text, []).request is not None or plan_turn(text).of_kind("image")
    ]
    assert drawn == []
