"""A draw-me line with a second request is declined exactly where the plan cuts it.

``asks_separately`` keeps "draw me a cat and also explain black holes" from drawing the
whole line: the plan draws the cat and answers the rest. It reads the plan's own cut
(``chat.cuts_after_picture``). A line it declines that the plan keeps whole draws nothing
at all (main drew it: "draw me a dog and tell me about dog breeds"); a line the plan cuts
that it lets through draws the whole line, question and all. Review 6 found 191 of 696
fuzzed lines drawn whole where the plan cut ("… and suggest names", ". Also …"), because
the old rule knew only nine answer verbs; the fuzz here is built from every opener the
plan cuts at.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.turn_prep.clauses import Cut, is_request
from app.modules.chat.turn_prep.intents import plan_turn
from app.modules.images.gen_intent import extract_image_gen_prompt
from app.modules.images.gen_intent_second import SECOND_ASKS, asks_separately
from app.modules.images.intent import composer_intent_for_chat
from app.tests.behavior.cases import CASES

_SWEEP = Path(__file__).resolve().parents[2] / "behavior" / "sweep_corpus"

# Kept whole by the plan, so drawn whole, as on main.
WHOLE = [
    "Draw me a dog and tell me about dog breeds",
    "Draw me a cat and tell me about cat breeds",
    "draw me a car and tell me which car is fastest",
    "draw me a cat and show the cat sleeping",
    "draw me a cat and how are you",
    "draw me a cat and tell me its name",
    "draw me a castle and help",
    "Draw me a cat then suggest names",
]
# Cut by the plan: the cat is drawn and the rest answered beside it.
CUT = [
    "draw me a cat and also explain black holes",
    "draw me a cat and explain black holes",
    "Draw me a dog and also tell me about dog breeds",
    "draw me a cat and tell me about cats",
    "draw me a sunset and what time is it in Tokyo",
    "draw me a robot and write a haiku about autumn",
    "Draw me a cat and also give me facts about cats",
    "Draw me a cat and suggest names",
    "Draw me a cat. Also explain black holes",
    "Draw me a cat. Also what is the capital of France",
    "Draw me a dog and remind me to call mom",
]

# The plan's task verbs (``clauses``): each opens a request of its own.
_TASK_VERBS = (
    "tell explain describe define write draft compose give show find search look google "
    "recommend suggest list compare translate summarize summarise teach draw create generate "
    "design plan solve calculate compute convert graph plot remind switch change set turn "
    "build implement debug review proofread rewrite brainstorm quiz check add make help"
).split()
# The plan's openers: every task verb, the question words and the auxiliaries, each with
# words of its own, after each connector it cuts at (or keeps whole).
_OPENERS = [
    *(f"{verb} me something about rain" for verb in _TASK_VERBS),
    *(
        f"{wh} {rest}"
        for wh, rest in (
            ("what", "is the capital of France"),
            ("who", "won the world cup"),
            ("when", "was Rome founded"),
            ("where", "is Lisbon"),
            ("why", "is the sky blue"),
            ("how", "do airplanes fly"),
            ("which", "planet is biggest"),
        )
    ),
    *(f"{aux} {rest}" for aux, rest in (("is", "it cold in Oslo?"), ("can", "you explain tides?"))),
    *(f"{aux} {rest}" for aux, rest in (("do", "cats dream?"), ("should", "I learn Python?"))),
    "I also want a story about a dragon",
    "tell me about cats",
    "tell me its name",
]
_CONNECTORS = [
    "and",
    "and also",
    "then",
    ", and also",
    ". Also",
    ", and",
    ";",
    ".",
    ". By the way,",
]
_SUBJECTS = ["a cat", "a red dragon"]


def _line(subject: str, connector: str, ask: str) -> str:
    if connector == ".":
        ask = ask[0].upper() + ask[1:]
    glue = connector if connector[0] in ",.;" else f" {connector}"
    return f"Draw me {subject}{glue} {ask}"


FUZZ = [_line(*parts) for parts in itertools.product(_SUBJECTS, _CONNECTORS, _OPENERS)]


def _plan_cuts(text: str) -> bool:
    plan = plan_turn(text)
    return plan.multi and [part.kind for part in plan.parts][:1] == ["image"]


def _corpus_lines() -> list[str]:
    """Every draw-me line with "and" before an answer word in the sweep and battery."""
    prompts = {case.prompt for case in CASES}
    for path in _SWEEP.glob("*.json"):
        prompts.update(entry["prompt"] for entry in json.loads(path.read_text()))
    return sorted(
        text
        for text in prompts
        if text.lower().startswith("draw me ")
        and any(f" and {ask} " in f" {text.lower()} " for ask in SECOND_ASKS)
    )


@pytest.mark.parametrize("text", WHOLE)
def test_a_line_the_plan_keeps_whole_draws_whole(text: str) -> None:
    assert not _plan_cuts(text)
    assert extract_image_gen_prompt(text)


@pytest.mark.parametrize("text", CUT)
def test_a_line_the_plan_cuts_draws_only_the_picture_part(text: str) -> None:
    assert _plan_cuts(text)
    assert extract_image_gen_prompt(text) is None


@pytest.mark.parametrize("text", sorted({*WHOLE, *CUT, *_corpus_lines()}))
def test_asks_separately_agrees_with_the_plan(text: str) -> None:
    assert asks_separately(text) == _plan_cuts(text)


def test_asks_separately_agrees_with_the_plan_on_every_opener() -> None:
    """Hundreds of lines, both ways: cut ones and ones the plan keeps whole."""
    assert all(is_request(ask, Cut.STRONG) for ask in _OPENERS)
    disagree = [text for text in FUZZ if asks_separately(text) != _plan_cuts(text)]
    assert not disagree
    cuts = sum(map(_plan_cuts, FUZZ))
    assert 0 < cuts < len(FUZZ) and len(FUZZ) >= 1000


@pytest.mark.parametrize(
    "text",
    [
        "draw me a cat and also explain black holes",
        "Draw me a cat. Also what is the capital of France",
        "Draw me a dog and suggest names",
    ],
)
async def test_a_cut_line_reads_nothing_on_the_event_loop(text: str) -> None:
    """The composer reader runs ``asks_separately`` inside a production coroutine, after
    the turn's one pool read. Every line here is cut, so it reaches ``is_picture`` and
    ``_keeps_cut``, and the suite's loop guard (``conftest._nothing_read_on_the_loop``)
    fails the test if either asks a reading or SymPy on the event loop."""
    verdict = await composer_intent_for_chat(Settings(), user_id=uuid4(), text=text, chat_id=None)
    assert verdict is not None and verdict.request is None
    assert asks_separately(text)
