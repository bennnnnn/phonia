"""The model reader: the server's checks, the two calls, and the verdict (docs/MODEL_READER.md).

The review's four wrong reads (2026-10-31) are cases here: a unit read at another scale, two
values swapped under quotes of the whole message, a substance the message never names, and
a number written with a leading decimal point.

The model is faked at the gateway (``structured_completion.complete_structured``); every
check and binder runs for real.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.gateways import litellm_gateway, structured_completion
from app.modules.math.tools.llm_extract import LLMMathExtract
from app.modules.model_reader.checks import check_read, normalized, values_in
from app.modules.model_reader.schemas import (
    GivenRead,
    LawRead,
    ModelRead,
    RouteRead,
    verdict,
)
from app.modules.model_reader.service import read_with_model

_SPEED = "A car travels 120 m in 8 s. What is its average speed?"


def _speed_read(**changes: Any) -> LawRead:
    read = LawRead(
        op="rate_speed",
        givens=[
            GivenRead(name="d", value=120, unit="m", quote="120 m"),
            GivenRead(name="t", value=8, unit="s", quote="8 s"),
        ],
    )
    return read.model_copy(update=changes)


# --- the checks ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("٣٫٥ m", "3٫5 m"),  # Arabic-Indic digits read as ASCII
        ("१२० मीटर", "120 मीटर"),  # Devanagari
        ("３ m", "3 m"),  # full-width
        ("3 × 10⁸ m/s", "3 × 10^8 m/s"),
        ("  Two   spaces ", "two spaces"),
    ],
)
def test_text_is_compared_with_ascii_digits_and_written_powers(text: str, plain: str) -> None:
    assert normalized(text) == plain


@pytest.mark.parametrize(
    ("quote", "value"),
    [("3 x 10^8 m/s", 3e8), ("3e8", 3e8), ("3,5 m", 3.5), ("3,000 kg", 3000.0), ("-2 m", -2.0)],
)
def test_a_quote_writes_its_value(quote: str, value: float) -> None:
    assert any(abs(seen - value) <= 1e-9 * abs(value) for seen in values_in(quote))


def test_a_read_of_the_message_is_ok() -> None:
    assert check_read(_SPEED, _speed_read()) == "ok"


def test_a_quote_the_message_never_wrote_is_the_models() -> None:
    read = _speed_read(givens=[GivenRead(name="d", value=120, unit="m", quote="120 metres")])
    assert check_read(_SPEED, read) == "quote_missing"


def test_a_value_its_quote_does_not_write_is_invented() -> None:
    read = _speed_read(
        givens=[
            GivenRead(name="d", value=0.12, unit="km", quote="120 m"),
            GivenRead(name="t", value=8, unit="s", quote="8 s"),
        ]
    )
    assert check_read(_SPEED, read) == "value_not_in_quote"


def test_a_number_the_read_dropped_is_a_misread() -> None:
    read = _speed_read(givens=[GivenRead(name="d", value=120, unit="m", quote="120 m")])
    assert check_read(_SPEED, read) == "number_unaccounted"


def test_a_number_with_a_leading_decimal_point_is_a_number() -> None:
    text = "A cart goes .5 km in 8 s. Find its average speed."
    read = LawRead(op="rate_speed", givens=[GivenRead(name="t", value=8, unit="s", quote="8 s")])
    assert check_read(text, read) == "number_unaccounted"


def test_quotes_of_the_whole_message_cannot_swap_values() -> None:
    read = _speed_read(
        givens=[
            GivenRead(name="d", value=8, unit="m", quote=_SPEED),
            GivenRead(name="t", value=120, unit="s", quote=_SPEED),
        ]
    )
    assert check_read(_SPEED, read) == "quote_not_one_value"


def test_two_values_cannot_come_from_one_place() -> None:
    text = "Each side is 4 m. Find the area."
    read = LawRead(
        op="x",
        givens=[
            GivenRead(name="a", value=4, unit="m", quote="4 m"),
            GivenRead(name="b", value=4, unit="m", quote="4 m"),
        ],
    )
    assert check_read(text, read) == "quotes_overlap"


def test_a_number_listed_as_unused_is_accounted_for() -> None:
    text = "Question 3. " + _SPEED
    assert check_read(text, _speed_read()) == "number_unaccounted"
    assert check_read(text, _speed_read(unused=["question 3"])) == "ok"


def test_names_and_powers_are_no_stated_numbers() -> None:
    text = "1.5 mol of H2O falls at 9.8 m/s² from v0. Find the time."
    read = LawRead(
        op="x",
        givens=[
            GivenRead(name="n", value=1.5, unit="mol", quote="1.5 mol"),
            GivenRead(name="g", value=9.8, unit="m/s^2", quote="9.8 m/s²"),
        ],
    )
    assert check_read(text, read) == "ok"


def test_a_question_in_amharic_digits_and_words_reads() -> None:
    text = "መኪና በ٨ ሰከንድ ውስጥ ١٢٠ ሜትር ተጓዘ። አማካይ ፍጥነቱ ስንት ነው?"
    read = LawRead(
        op="rate_speed",
        givens=[
            GivenRead(name="d", value=120, unit="m", quote="١٢٠ ሜትር"),
            GivenRead(name="t", value=8, unit="s", quote="٨ ሰከንድ"),
        ],
    )
    assert check_read(text, read) == "ok"


# --- the two calls ---------------------------------------------------------------


def _fake(replies: list[BaseModel | None]) -> Any:
    calls: list[str] = []

    async def complete_structured(**kwargs: Any) -> BaseModel | None:
        calls.append(kwargs["schema"].__name__)
        kwargs["usage"]["input"] = kwargs["usage"].get("input", 0) + 100
        return replies.pop(0)

    complete_structured.calls = calls  # type: ignore[attr-defined]
    return complete_structured


@pytest.mark.asyncio
async def test_a_physics_question_reads_to_the_binders_intent(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    fake = _fake([RouteRead(subject="physics", kind="kinematics"), _speed_read()])
    monkeypatch.setattr(structured_completion, "complete_structured", fake)
    read = await read_with_model(_SPEED, Settings())
    assert (read.subject, read.op, read.reason) == ("physics", "rate_speed", "ok")
    assert getattr(read.intent, "physics_params", None) == {"d": 120.0, "t": 8.0}
    assert fake.calls == ["RouteRead", "LawRead"] and read.input_tokens == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("replies", "reason"),
    [
        ([None], "no_read"),
        ([RouteRead(subject="none")], "not_subject"),
        ([RouteRead(subject="physics", kind="astrology")], "unknown_kind"),
        ([RouteRead(subject="physics", kind="kinematics"), LawRead(op="none")], "no_read"),
        (
            [RouteRead(subject="physics", kind="kinematics"), _speed_read(op="ohms_law")],
            "unknown_op",
        ),
        (
            [
                RouteRead(subject="physics", kind="kinematics"),
                _speed_read(givens=[GivenRead(name="d", value=120, unit="m", quote="120 m")]),
            ],
            "number_unaccounted",
        ),
        (
            # 120 m read as 120 cm: the quote writes another scale.
            [
                RouteRead(subject="physics", kind="kinematics"),
                _speed_read(
                    givens=[
                        GivenRead(name="d", value=120, unit="cm", quote="120 m"),
                        GivenRead(name="t", value=8, unit="s", quote="8 s"),
                    ]
                ),
            ],
            "binder_disagrees",
        ),
        (
            # The units are swapped: the binder cannot take a time in metres.
            [
                RouteRead(subject="physics", kind="kinematics"),
                _speed_read(
                    givens=[
                        GivenRead(name="d", value=120, unit="s", quote="120 m"),
                        GivenRead(name="t", value=8, unit="m", quote="8 s"),
                    ]
                ),
            ],
            "binder_disagrees",
        ),
    ],
)
async def test_a_read_that_fails_a_check_gives_no_intent(
    monkeypatch: pytest.MonkeyPatch,
    thread_sympy_executor: None,
    replies: list[BaseModel | None],
    reason: str,
) -> None:
    monkeypatch.setattr(structured_completion, "complete_structured", _fake(replies))
    read = await read_with_model(_SPEED, Settings())
    assert read.reason == reason and read.intent is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "extract", "reason"),
    [
        # A task the typed read cannot express is refused, never read as the nearest one.
        (RouteRead(subject="math", kind="other"), None, "other_task"),
        (RouteRead(subject="math", kind="prove"), None, "other_task"),
        # Routed as a derivative, read as an equation: not the task asked.
        (
            RouteRead(subject="math", kind="differentiate"),
            LLMMathExtract(found=True, kind="equation", lhs="2*x+3", rhs="11"),
            "kind_mismatch",
        ),
        (
            RouteRead(subject="math", kind="solve_equation"),
            LLMMathExtract(found=True, kind="equation", lhs="2*x+3", rhs="11"),
            "ok",
        ),
    ],
)
async def test_a_maths_read_must_be_the_task_it_was_routed_as(
    monkeypatch: pytest.MonkeyPatch,
    route: RouteRead,
    extract: LLMMathExtract | None,
    reason: str,
) -> None:
    monkeypatch.setattr(structured_completion, "complete_structured", _fake([route]))
    monkeypatch.setattr(litellm_gateway, "complete_structured", _fake([extract]))
    read = await read_with_model("Solve 2x + 3 = 11", Settings())
    assert read.reason == reason
    assert (read.intent is not None) is (reason == "ok")


@pytest.mark.asyncio
@pytest.mark.parametrize("quote", ["300", "300 cm"])
async def test_a_unit_read_at_another_scale_than_the_message_writes_binds_nothing(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None, quote: str
) -> None:
    reads: list[BaseModel | None] = [
        RouteRead(subject="physics", kind="kinematics"),
        LawRead(
            op="rate_speed",
            givens=[
                GivenRead(name="d", value=300, unit="m", quote=quote),
                GivenRead(name="t", value=8, unit="s", quote="8 s"),
            ],
        ),
    ]
    monkeypatch.setattr(structured_completion, "complete_structured", _fake(reads))
    read = await read_with_model(
        "A toy car rolls 300 cm in 8 s. Find its average speed.", Settings()
    )
    assert read.reason == "binder_disagrees" and read.intent is None


@pytest.mark.asyncio
async def test_a_substance_the_message_never_names_binds_nothing(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    from app.modules.chemistry.model_read import chemistry_menu

    kind = next(
        kind
        for kind, cards in chemistry_menu().items()
        if any(c.op == "strong_acid_ph" for c in cards)
    )
    message = "What is the pH of 0.01 M HCl?"

    def law(formula: str) -> LawRead:
        return LawRead(
            op="strong_acid_ph",
            givens=[GivenRead(name="concentration", value=0.01, unit="mol/L", quote="0.01 M")],
            formula=formula,
        )

    monkeypatch.setattr(
        structured_completion,
        "complete_structured",
        _fake([RouteRead(subject="chemistry", kind=kind), law("HBr")]),
    )
    assert (await read_with_model(message, Settings())).reason == "binder_disagrees"
    monkeypatch.setattr(
        structured_completion,
        "complete_structured",
        _fake([RouteRead(subject="chemistry", kind=kind), law("HCl")]),
    )
    assert (await read_with_model(message, Settings())).reason == "ok"


@pytest.mark.asyncio
async def test_a_failing_gateway_is_a_reason_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(**_kwargs: Any) -> None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(structured_completion, "complete_structured", broken)
    read = await read_with_model(_SPEED, Settings())
    assert read.reason == "failed" and read.intent is None


# --- the verdict -----------------------------------------------------------------


def _read(subject: str | None, op: str | None, reason: str = "ok") -> ModelRead:
    return ModelRead(subject, op, object(), reason, 1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("regex", "read", "expected"),
    [
        (("physics", "rate_speed"), _read("physics", "rate_speed"), "agree"),
        (("physics", "average_speed"), _read("physics", "rate_speed"), "other_op"),
        (("physics", "rate_speed"), _read("chemistry", "molarity"), "disagree"),
        (("math", "solve"), _read("math", "equation"), "agree"),
        (("physics", "rate_speed"), _read(None, None, "not_subject"), "regex_only"),
        ((None, None), _read("physics", "rate_speed"), "model_only"),
        ((None, None), _read("physics", "rate_speed", "binder_disagrees"), "neither"),
        ((None, None), None, "neither"),
    ],
)
def test_the_verdict_compares_the_two_reads(
    regex: tuple[str | None, str | None], read: ModelRead | None, expected: str
) -> None:
    assert verdict(regex[0], regex[1], read) == expected
