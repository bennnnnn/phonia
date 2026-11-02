"""Word problems: translated by a model, trusted only once SymPy closes them."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway
from app.models.routing_lanes import ROUTING
from app.modules.math import tools as mt
from app.modules.math.schemas import MathIntent
from app.modules.math.schemas.word_problem import WordProblemSetup
from app.modules.math.solve.word_problem import solve_word_problem
from app.modules.math.tools import prompt as math_prompt
from app.modules.math.tools.direct import maybe_direct_math_reply
from app.modules.math.tools.word_problem import (
    grounded,
    word_problem_candidate,
    word_problem_intent,
)

AGES = (
    "Maria is three times as old as her son. Together their ages add up to 48. How old is her son?"
)
AGES_SETUP: dict[str, Any] = {
    "found": True,
    "unknowns": [
        {"symbol": "m", "meaning": "Maria's age now", "unit": "years"},
        {"symbol": "s", "meaning": "her son's age now", "unit": "years"},
    ],
    "equations": [
        {"equation": "m = 3*s", "source": "Maria is three times as old as her son"},
        {"equation": "m + s = 48", "source": "Together their ages add up to 48"},
    ],
    "targets": [{"expr": "s", "meaning": "her son's age", "unit": "years"}],
    "whole_numbers": True,
    "positive": True,
}
TICKETS = (
    "Tickets cost $5 for kids and $8 for adults. 20 people paid $124 in total. "
    "How many adults went?"
)
TICKETS_SETUP: dict[str, Any] = {
    "found": True,
    "unknowns": [
        {"symbol": "k", "meaning": "number of kids"},
        {"symbol": "a", "meaning": "number of adults"},
    ],
    "equations": [{"equation": "k + a = 20"}, {"equation": "5*k + 8*a = 124"}],
    "targets": [{"expr": "a", "meaning": "adults who went"}],
    "whole_numbers": True,
    "positive": True,
}
CONSECUTIVE = "Three consecutive integers add up to 72. Find the integers."
CONSECUTIVE_SETUP: dict[str, Any] = {
    "found": True,
    "unknowns": [{"symbol": "n", "meaning": "the smallest integer"}],
    "equations": [{"equation": "n + (n + 1) + (n + 2) = 72"}],
    "targets": [
        {"expr": "n", "meaning": "first"},
        {"expr": "n + 1", "meaning": "second"},
        {"expr": "n + 2", "meaning": "third"},
    ],
    "whole_numbers": True,
}
PENCIL = (
    "A pen costs $1.50 more than a pencil. Together they cost $2.10. What does the pencil cost?"
)
PENCIL_SETUP: dict[str, Any] = {
    "found": True,
    "unknowns": [{"symbol": "p", "meaning": "price of the pencil", "unit": "$"}],
    "equations": [{"equation": "p + (p + 1.50) = 2.10"}],
    "targets": [{"expr": "p", "meaning": "the pencil costs", "unit": "$"}],
    "positive": True,
}
BOOKS = (
    "If Abebe has 10 red books and some green books, then gives away 5 green books "
    "and has 10 books left, how many green books did Abebe have at first?"
)
BOOKS_SETUP: dict[str, Any] = {
    "found": True,
    "unknowns": [
        {
            "symbol": "g",
            "meaning": "green books Abebe had at first",
            "unit": "books",
        }
    ],
    "equations": [
        {
            "equation": "10 + g - 5 = 10",
            "source": "10 red books, gives away 5 green books, and has 10 books left",
        }
    ],
    "targets": [
        {
            "expr": "g",
            "meaning": "green books Abebe had at first",
            "unit": "books",
        }
    ],
    "whole_numbers": True,
    "positive": True,
}


def _setup(base: dict[str, Any], **overrides: Any) -> WordProblemSetup:
    return WordProblemSetup.model_validate({**base, **overrides})


def _settings(**overrides: Any) -> Settings:
    return Settings(**{"math_tools_enabled": True, **overrides})


def _gateway(payload: dict[str, Any] | None) -> Any:
    async def fake(*, schema: type, **kwargs: Any) -> Any:
        if schema is not WordProblemSetup or payload is None:
            return None
        return WordProblemSetup.model_validate(payload)

    return fake


# --- the gate ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        AGES,
        TICKETS,
        CONSECUTIVE,
        PENCIL,
        "A number plus 7 is 19. What is the number?",
        "A number plus 7 is 19. Work out the number.",
        "A number plus 7 is 19. What is it?",
        "If a number plus 5 equals 12, find it.",
        "Tom and Ana have 10 apples together. Tom has 3. What does Ana have?",
        "What number is 5 more than 7?",
        "Which integer is 9 less than 20?",
        "The sum of two numbers is 30 and their difference is 6. What are the numbers?",
        "John has 5 more apples than Sam. Together they have 23 apples. How many does Sam have?",
        BOOKS,
        "A shop had some notebooks, received 8, sold 3, and now has 20. How many did it start with?",
        "Jane has 8 apples and gives 3 to Joe. How many does she have now?",
        "Jane has 10 apples and gives 3 away. What is left?",
        "Jane has 8 apples and receives 3 from Joe. How many does she have now?",
        "Marta had 12 blue beads and some red beads, lost 4 red beads, and has 15 left. "
        "How many red beads did she start with?",
        "24 candies are shared equally among 6 children. How much will each child get?",
        "A number plus 5 equals 12. Solve for the number?",
        "Maria spent $5 and has $10 left. How much did she have initially?",
        "A shop spent $5 and has $10 left. How much did it start with?",
        "Maria spent $5 and has $10 left. How much did she have before?",
        "Maria spent $5 and has $10 left. How much did she have previously?",
        # A stated rate scaled to a third amount: a proportion.
        "A recipe needs 3 cups of flour for 12 cookies. How many cups for 30 cookies?",
        "A recipe needs 3 cups of flour for 12 cookies. How many cups do I need if I want to "
        "bake 30 cookies?",
        "2 eggs make 8 pancakes. How many eggs are in 20 pancakes?",
    ],
)
def test_candidate_fires_for_algebra_word_problems(text: str) -> None:
    assert word_problem_candidate(text)


@pytest.mark.parametrize(
    "text",
    [
        "How many people live in Paris?",
        "How many calories are in two eggs and three slices of bacon in total?",
        "I have 3 cats and 2 dogs, what should I name them?",
        "I got 3 cats and 2 dogs, what should I name them?",
        "I got 3 cats and 2 dogs. What does that make me?",
        "I got 3 cats and 2 dogs. What is a good name for them?",
        "I got 3 cats and 2 dogs. Find names for them.",
        "I bought 3 books and 2 games. How much did you enjoy them?",
        "I got 3 cats and 2 dogs. What is it?",
        "I got 3 cats and 2 dogs. Find them.",
        "I got 3 cats and 2 dogs. What does Ana have?",
        "I got 3 cats and 2 dogs. How many should I adopt?",
        "I got 3 cats and 2 dogs. How many total would you recommend I adopt?",
        "I bought 3 books and 2 games. How many did you enjoy?",
        "I bought 3 books and 2 games. Can you work out which I should play first?",
        "solve 2x+3=11",
        "Find 2 + 2",
        "A ball is thrown straight up at 20 m/s. How high does it go in total?",
        "What is the sum of 3 and 4? " * 40,
        # A stated rate with no third amount to scale it to.
        "I booked 2 rooms for 3 nights. How many towels come with that?",
        "A recipe needs 3 cups of flour for 12 cookies, how many cups is that?",
    ],
)
def test_candidate_declines(text: str) -> None:
    assert not word_problem_candidate(text)


@pytest.mark.parametrize(
    "text",
    [
        "I got 3 cats and 2 dogs, what should I name them?",
        "I got 3 cats and 2 dogs. What does that make me?",
        "I got 3 cats and 2 dogs. What is a good name for them?",
        "I got 3 cats and 2 dogs. Find names for them.",
        "I bought 3 books and 2 games. How much did you enjoy them?",
        "I got 3 cats and 2 dogs. What is it?",
        "I got 3 cats and 2 dogs. Find them.",
        "I got 3 cats and 2 dogs. What does Ana have?",
        "I got 3 cats and 2 dogs. How many should I adopt?",
        "I got 3 cats and 2 dogs. How many total would you recommend I adopt?",
        "I bought 3 books and 2 games. How many did you enjoy?",
        "I bought 3 books and 2 games. Can you work out which I should play first?",
    ],
)
def test_non_math_possession_question_does_not_enter_math_pipeline(text: str) -> None:
    assert not word_problem_candidate(text)
    assert not mt.needs_symbolic_math(text)


def test_gate_opens_for_a_word_problem() -> None:
    assert mt.needs_symbolic_math(AGES)


# --- the number guard ------------------------------------------------------------


@pytest.mark.parametrize(
    "text, equation",
    [
        (AGES, "m = 3*s"),
        (AGES, "m + s = 48"),
        (CONSECUTIVE, "n + (n + 1) + (n + 2) = 72"),
        (PENCIL, "p + (p + 1.5) = 2.1"),
        ("Half of a number is 9. What is the number?", "0.5*n = 9"),
        ("Half of a number is 9. What is the number?", "n/2 = 9"),
        ("After a 20% discount a shirt costs $40. What was the price?", "p - 0.2*p = 40"),
        ("After a 20% discount a shirt costs $40. What was the price?", "p*(100 - 20)/100 = 40"),
        ("A dozen eggs cost $3 more than 6 apples. Find the cost.", "c = 12"),
        ("Half of a number is 9. What is the number?", "1/2*n = 9"),
        ("After a 20% discount a shirt costs $40. What was the price?", "p*(1 - 0.2) = 40"),
        ("After a 20% discount a shirt costs $40. What was the price?", "p*(1 - 20/100) = 40"),
        ("A third of the class left and 20 stayed. How many were there?", "n*(1 - 1/3) = 20"),
        ("One more than twice a number is 15. What is the number?", "2*n + 1 = 15"),
    ],
)
def test_grounded_accepts_numbers_the_problem_states(text: str, equation: str) -> None:
    setup = _setup(
        AGES_SETUP, equations=[{"equation": equation}], targets=[{"expr": "n", "meaning": "x"}]
    )
    assert grounded(setup, text)


@pytest.mark.parametrize(
    "text, equation",
    [
        (
            "John has 5 more apples than Sam. Together they have 23 apples. How many does Sam have?",
            "s + (s + 7) = 23",
        ),
        # A 1 the problem never implies.
        ("A number plus 7 is 19. What is the number?", "n + 1 = 19"),
        ("After a 20% discount a shirt costs $40. What was the price?", "p + 1 - 0.2*p = 40"),
        ("After a 20% discount a shirt costs $40. What was the price?", "p*(1 - 0.3) = 40"),
        ("Half of a number is 9. What is the number?", "1/3*n = 9"),
    ],
)
def test_grounded_refuses_a_smuggled_number(text: str, equation: str) -> None:
    setup = _setup(
        AGES_SETUP, equations=[{"equation": equation}], targets=[{"expr": "n", "meaning": "x"}]
    )
    assert not grounded(setup, text)


def test_grounded_checks_targets_too() -> None:
    setup = _setup(AGES_SETUP, targets=[{"expr": "s + 4", "meaning": "age in 4 years"}])
    assert not grounded(setup, AGES)


# --- solving ---------------------------------------------------------------------


def test_solve_ages() -> None:
    solution = solve_word_problem(_setup(AGES_SETUP))
    assert solution is not None
    assert dict(solution.values) == {"m": 36, "s": 12}
    assert solution.answers == (12,)
    assert solution.steps and solution.check is not None
    assert solution.equations == ("m = 3 \\cdot s", "m + s = 48")


def test_solve_tickets_as_a_system() -> None:
    solution = solve_word_problem(_setup(TICKETS_SETUP))
    assert solution is not None
    assert dict(solution.values) == {"k": 12, "a": 8}
    assert solution.steps[0].label == "Solve equation (1) for k"


def test_solve_consecutive_integers_shows_the_combining_step() -> None:
    solution = solve_word_problem(_setup(CONSECUTIVE_SETUP))
    assert solution is not None
    assert solution.answers == (23, 24, 25)
    assert solution.steps[0].label == "Simplify"
    assert solution.steps[0].formula == "3 n + 3 = 72"
    assert solution.equations == ("n + (n + 1) + (n + 2) = 72",)


def test_solve_keeps_one_root_that_fits_the_domain() -> None:
    setup = _setup(
        AGES_SETUP,
        unknowns=[{"symbol": "w", "meaning": "width"}],
        equations=[{"equation": "w*(w + 3) = 40"}],
        targets=[{"expr": "w", "meaning": "width"}],
    )
    solution = solve_word_problem(setup)
    assert solution is not None and solution.answers == (5,)


@pytest.mark.parametrize(
    "overrides",
    [
        # A fractional count is a misreading, not an answer.
        {"equations": [{"equation": "k + a = 20"}, {"equation": "5*k + 8*a = 125"}]},
        # Two roots both fit: the problem is ambiguous as read.
        {
            "unknowns": [{"symbol": "n", "meaning": "n"}],
            "equations": [{"equation": "n^2 + 6 = 5*n"}],
            "targets": [{"expr": "n", "meaning": "n"}],
        },
        # A negative age.
        {"equations": [{"equation": "k + 30 = 20"}, {"equation": "a = 1"}]},
        # An unknown the setup never declared.
        {"equations": [{"equation": "k + q = 20"}, {"equation": "5*k + 8*a = 124"}]},
        # Fewer equations than unknowns.
        {"equations": [{"equation": "k + a = 20"}]},
        # No equals sign, or two.
        {"equations": [{"equation": "k + a"}, {"equation": "5*k + 8*a = 124"}]},
        {"equations": [{"equation": "k = a = 20"}, {"equation": "5*k + 8*a = 124"}]},
        # Inconsistent.
        {"equations": [{"equation": "k + a = 20"}, {"equation": "k + a = 21"}]},
        # A reserved letter.
        {"unknowns": [{"symbol": "e", "meaning": "e"}, {"symbol": "a", "meaning": "a"}]},
        # Nothing asked.
        {"targets": []},
        {"found": False},
        # A target that names no unknown would show a stated number as the answer.
        {"targets": [{"expr": "20", "meaning": "adults who went"}]},
        {"targets": [{"expr": "a - a + 20", "meaning": "adults who went"}]},
    ],
)
def test_solve_refuses(overrides: dict[str, Any]) -> None:
    assert solve_word_problem(_setup(TICKETS_SETUP, **overrides)) is None


# --- replies ---------------------------------------------------------------------


def _reply(payload: dict[str, Any], text: str) -> str | None:
    intent = MathIntent(
        kind="word_problem",
        word_problem=WordProblemSetup.model_validate(payload),
        operation="solve",
    )
    block = mt._build_verified_block(intent, _settings())
    assert block is not None
    return maybe_direct_math_reply(block, text)


def test_reply_shows_setup_steps_and_answer() -> None:
    reply = _reply(AGES_SETUP, AGES)
    assert reply is not None
    # Given: each equation with the words it comes from. Required: what each letter is.
    assert (
        "**Required**  \n$m$ — Maria's age now (years)  \n$s$ — her son's age now (years)" in reply
    )
    assert '$m = 3 \\times s$ — "Maria is three times as old as her son"' in reply
    # The lesson layout: bold numbered moves with their rule; no check unless asked.
    assert "**Steps**" not in reply and "Check" not in reply
    assert "**1. Substitute into equation (2)** — " in reply
    assert "her son's age: $12$ years" in reply
    assert reply.rstrip().endswith("```answer\n12\\ \\text{years}\n```")


def test_money_answer_reads_as_dollars() -> None:
    reply = _reply(PENCIL_SETUP, PENCIL)
    assert reply is not None
    assert "the pencil costs: $0.30$ dollars" in reply
    assert "```answer\n\\$0.30\n```" in reply
    assert "**1. Simplify**" in reply
    assert (
        "**2. Subtract $\\frac{3}{2}$ from both sides** — Subtraction property of equality" in reply
    )
    # The last move ends on the solved letter, not on a separate "Result" step.
    assert "Result" not in reply and "$p = \\frac{3}{10}$" in reply


def test_inventory_change_problem_shows_equation_working() -> None:
    reply = _reply(BOOKS_SETUP, BOOKS)

    assert reply is not None
    assert "$10 + g - 5 = 10$" in reply
    assert "**Steps**" not in reply
    assert "$g = 5$" in reply
    assert "Check" not in reply
    assert "green books Abebe had at first: $5$ books" in reply


def test_word_problem_check_only_when_asked() -> None:
    reply = _reply(BOOKS_SETUP, f"{BOOKS} and check it")
    assert reply is not None
    moves = "$g = 5$\n\n**3. Check**  \n$(5) + 5 = 10$\n\ngreen books"
    assert moves in reply


def test_reply_strips_markup_from_the_translation() -> None:
    payload = {
        **AGES_SETUP,
        "unknowns": [
            {"symbol": "m", "meaning": "**Maria** `age` [link](x) $\\evil$"},
            {"symbol": "s", "meaning": "son", "unit": "years}\\"},
        ],
    }
    reply = _reply(payload, AGES)
    assert reply is not None
    for leaked in ("**Maria**", "`age`", "[link]", "\\evil", "(years}\\)"):
        assert leaked not in reply


def test_photo_attached_keeps_the_model_path() -> None:
    intent = MathIntent(
        kind="word_problem",
        word_problem=WordProblemSetup.model_validate(AGES_SETUP),
        operation="solve",
    )
    block = mt._build_verified_block(intent, _settings())
    assert block is not None
    assert maybe_direct_math_reply(block, AGES, has_image_attachment=True) is None


# --- extraction and the turn --------------------------------------------------------


@pytest.mark.asyncio
async def test_intent_makes_no_call_when_off_or_not_a_word_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(**kwargs: Any) -> None:
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(litellm_gateway, "complete_structured", boom)
    assert await word_problem_intent(AGES, _settings(math_word_problems_enabled=False)) is None
    assert await word_problem_intent("How many people live in Paris?", _settings()) is None


@pytest.mark.asyncio
async def test_intent_uses_resilient_bounded_structured_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> WordProblemSetup:
        seen.update(kwargs)
        return WordProblemSetup.model_validate(AGES_SETUP)

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    intent = await word_problem_intent(AGES, _settings())
    assert intent is not None and intent.kind == "word_problem"
    assert seen["model_alias"] == ROUTING.word_problems
    assert seen["schema"] is WordProblemSetup
    assert seen["allow_fallback"] is False


@pytest.mark.asyncio
async def test_intent_retries_semantic_decline_on_independent_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aliases: list[str] = []

    async def fake(**kwargs: Any) -> WordProblemSetup:
        aliases.append(kwargs["model_alias"])
        payload = {"found": False} if len(aliases) == 1 else AGES_SETUP
        return WordProblemSetup.model_validate(payload)

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    intent = await word_problem_intent(AGES, _settings())

    assert intent is not None and intent.kind == "word_problem"
    assert aliases == [ROUTING.word_problems, ROUTING.structured_fallback]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"found": False},
        {**AGES_SETUP, "equations": [{"equation": "m = 7*s"}, {"equation": "m + s = 48"}]},
        # A 1 the problem never states.
        {**AGES_SETUP, "equations": [{"equation": "m = 3*s + 1"}, {"equation": "m + s = 48"}]},
    ],
)
async def test_intent_refuses_missing_or_ungrounded(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any] | None
) -> None:
    monkeypatch.setattr(litellm_gateway, "complete_structured", _gateway(payload))
    assert await word_problem_intent(AGES, _settings()) is None


@pytest.mark.asyncio
async def test_intent_survives_a_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raises(**kwargs: Any) -> None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(litellm_gateway, "complete_structured", raises)
    assert await word_problem_intent(AGES, _settings()) is None


@pytest.mark.asyncio
async def test_intent_rejects_an_unrepresented_second_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(litellm_gateway, "complete_structured", _gateway(AGES_SETUP))
    text = f"{AGES} Then graph it."
    assert await word_problem_intent(text, _settings()) is None


@pytest.mark.asyncio
async def test_a_translated_turn_is_an_unchecked_setup_for_the_model(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    """SymPy checks the translation's arithmetic, not that it says what the problem says:
    the model gets the setup and its solution to check, and no card is verified."""
    monkeypatch.setattr(litellm_gateway, "complete_structured", _gateway(TICKETS_SETUP))
    note, verified = await math_prompt.build_math_augmentation(TICKETS, _settings())
    assert verified is None
    assert note is not None
    assert "Equation: 5 \\cdot k + 8 \\cdot a = 124" in note
    assert "SymPy's solution of these equations: k = 12, a = 8" in note


def test_a_template_setup_replies_directly() -> None:
    """A setup the server read keeps its verified, direct reply."""
    setup = WordProblemSetup.model_validate(TICKETS_SETUP).as_read_from_text()
    intent = MathIntent(kind="word_problem", word_problem=setup, operation="solve")
    verified = mt._build_verified_block(intent, _settings())
    assert verified is not None and verified.canonical_answer == "8"
    reply = maybe_direct_math_reply(verified, TICKETS)
    assert reply is not None and "adults who went: $8$" in reply


@pytest.mark.asyncio
async def test_turn_with_an_unverifiable_translation_keeps_the_honesty_note(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    # Every number is stated, but the reading gives 140/3 kids: SymPy refuses it.
    payload = {
        **TICKETS_SETUP,
        "equations": [{"equation": "k + a = 20"}, {"equation": "5*k + 8*a = 20"}],
    }
    monkeypatch.setattr(litellm_gateway, "complete_structured", _gateway(payload))
    note, verified = await math_prompt.build_math_augmentation(TICKETS, _settings())
    assert verified is None
    assert note is not None and "could not be produced" in note
