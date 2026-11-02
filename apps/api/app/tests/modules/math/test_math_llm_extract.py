"""LLM-structured extraction fallback (gate-fired + regex-None path only)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.gateways import litellm_gateway
from app.models.routing_lanes import ROUTING
from app.modules.math.schemas import MathIntent
from app.modules.math.tools import prompt as math_prompt
from app.modules.math.tools.llm_extract import (
    LLMMathExtract,
    llm_extract_math_intent,
    to_math_intent,
)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"math_tools_enabled": True, "math_llm_extract_enabled": True}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# --- to_math_intent mapping -------------------------------------------------


def test_to_math_intent_maps_equation() -> None:
    intent = to_math_intent(
        LLMMathExtract(found=True, kind="equation", lhs="3*x+5", rhs="17", variable="x")
    )
    assert intent == MathIntent(
        kind="equation", lhs="3*x+5", rhs="17", operation="solve", variable="x"
    )


def test_to_math_intent_maps_calculus_with_definite_bounds() -> None:
    intent = to_math_intent(
        LLMMathExtract(
            found=True, kind="calculus", operation="integrate", expr="x^2", lower="0", upper="3"
        )
    )
    assert intent is not None
    assert intent.kind == "calculus"
    assert intent.operation == "integrate"
    assert intent.integral_lower == "0"
    assert intent.integral_upper == "3"


def test_to_math_intent_maps_system_of_four() -> None:
    eqs = [(f"x+{i}", str(i)) for i in range(4)]
    intent = to_math_intent(
        LLMMathExtract(found=True, kind="system", equations=eqs, variables=["x", "y"])
    )
    assert intent is not None
    assert intent.system_equations == eqs


def test_to_math_intent_rejects_system_longer_than_four() -> None:
    eqs = [(f"x+{i}", str(i)) for i in range(6)]
    assert (
        to_math_intent(
            LLMMathExtract(found=True, kind="system", equations=eqs, variables=["x", "y"])
        )
        is None
    )


@pytest.mark.parametrize(
    "extract",
    [
        LLMMathExtract(found=False),
        LLMMathExtract(found=True, kind=None),
        LLMMathExtract(found=True, kind="equation", lhs="x+1"),  # missing rhs
        LLMMathExtract(found=True, kind="calculus", expr="x^2"),  # missing operation
        LLMMathExtract(found=True, kind="limit", expr="sin(x)/x"),  # missing point
        LLMMathExtract(found=True, kind="graph"),  # missing expr
        LLMMathExtract(found=True, kind="inequality", lhs="x", rhs="1"),  # no comparator
    ],
)
def test_to_math_intent_rejects_incomplete(extract: LLMMathExtract) -> None:
    assert to_math_intent(extract) is None


# --- llm_extract_math_intent ------------------------------------------------


@pytest.mark.asyncio
async def test_llm_extract_disabled_by_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**kwargs: object) -> None:
        raise AssertionError("gateway must not be called when the flag is off")

    monkeypatch.setattr(litellm_gateway, "complete_structured", _boom)
    assert (
        await llm_extract_math_intent("2x+3=7", _settings(math_llm_extract_enabled=False)) is None
    )


@pytest.mark.asyncio
async def test_llm_extract_returns_mapped_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(**kwargs: object) -> LLMMathExtract:
        assert kwargs["model_alias"] == ROUTING.math_extract
        assert kwargs["allow_fallback"] is True
        assert kwargs["fallback_on_invalid"] is True
        return LLMMathExtract(found=True, kind="equation", lhs="3*x+5", rhs="17")

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    intent = await llm_extract_math_intent(
        "solve the equation three x plus five equals seventeen", _settings()
    )
    assert intent is not None and intent.kind == "equation" and intent.rhs == "17"


@pytest.mark.asyncio
async def test_llm_extract_none_and_exception_degrade_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def returns_none(**kwargs: object) -> None:
        return None

    monkeypatch.setattr(litellm_gateway, "complete_structured", returns_none)
    assert await llm_extract_math_intent("some math", _settings()) is None

    def raises(**kwargs: object) -> None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(litellm_gateway, "complete_structured", raises)
    assert await llm_extract_math_intent("some math", _settings()) is None


# --- build_math_augmentation wiring -----------------------------------------


@pytest.mark.asyncio
async def test_fallback_only_runs_when_gate_fired_and_regex_missed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: regex extraction succeeds → zero LLM extraction calls."""
    calls = 0

    async def fake(**kwargs: object) -> None:
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    _note, verified = await math_prompt.build_math_augmentation("2x+3=7", _settings())
    assert calls == 0
    assert verified is not None  # regex path verified it without the LLM


@pytest.mark.asyncio
async def test_fallback_skipped_when_gate_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fake(**kwargs: object) -> None:
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "what is the capital of France", _settings()
    )
    assert calls == 0
    assert note is None and verified is None


@pytest.mark.asyncio
async def test_fallback_verifies_the_users_own_maths_regex_missed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ∫ x² scar class: gate fires, regex returns None, LLM extract + SymPy close it.
    The extraction is certified because x^2 is what the user wrote; read from "x squared"
    it is the model's reading and is not (``test_math_model_readings.py``)."""
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(found=True, kind="calculus", operation="integrate", expr="x^2")

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "Integrate x^2 please", _settings(), needs_math=True
    )
    assert verified is not None
    assert verified.canonical_answer is not None
    assert verified.canonical_answer is not None
    assert "x" in verified.canonical_answer and "3" in verified.canonical_answer
    assert note is not None and "Couldn't verify" not in note


@pytest.mark.asyncio
async def test_fallback_found_false_keeps_honesty_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(found=False)

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "find the angle", _settings(), needs_math=True
    )
    assert verified is None
    assert note is not None and "No verified solver result is available" in note


@pytest.mark.asyncio
async def test_fallback_unverifiable_candidate_gets_unverified_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM proposes, SymPy disposes: an expr SymPy cannot parse must not verify. It is not
    the user's maths either, so it never reaches SymPy: the turn has no verified result."""
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(
            found=True, kind="calculus", operation="integrate", expr="@@@ not math @@@"
        )

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "integrate something", _settings(), needs_math=True
    )
    assert verified is None
    assert note is not None
    assert "No verified solver result is available" in note
    assert "Do not claim verification" in note


@pytest.mark.asyncio
async def test_fallback_equation_with_restricted_trig_domain_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same guard as the OCR path: don't certify an all-real answer when the
    user named a domain the trig solver doesn't own."""
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(found=True, kind="equation", lhs="sin(x)", rhs="1/2")

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "solve sin(x) = 1/2 for x in [0, pi]", _settings(), needs_math=True
    )
    assert verified is None
    assert note is not None and "No verified solver result is available" in note


@pytest.mark.asyncio
async def test_fallback_equation_with_nondefault_domain_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The structured fallback must obey the same whole-request audit as regex extraction."""
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(found=True, kind="equation", lhs="x^2", rhs="4")

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "Solve x^2=4 where x is positive", _settings(), needs_math=True
    )
    assert verified is None
    assert note is not None and "No verified solver result is available" in note


@pytest.mark.asyncio
async def test_fallback_system_with_nondefault_domain_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(
            found=True,
            kind="system",
            equations=[("x+y", "1"), ("x-y", "0")],
            variables=["x", "y"],
        )

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "Solve x+y=1, x-y=0 over the integers", _settings(), needs_math=True
    )
    assert verified is None
    assert note is not None and "No verified solver result is available" in note


@pytest.mark.asyncio
async def test_fallback_inequality_with_nondefault_domain_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(math_prompt, "extract_math_intent", lambda _text: None)

    async def fake(**kwargs: object) -> LLMMathExtract:
        return LLMMathExtract(
            found=True,
            kind="inequality",
            lhs="x^2",
            rhs="4",
            comparator="<",
            variable="x",
        )

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    note, verified = await math_prompt.build_math_augmentation(
        "Solve x^2 < 4 over the integers", _settings(), needs_math=True
    )
    assert verified is None
    assert note is not None and "No verified solver result is available" in note


@pytest.mark.asyncio
async def test_fallback_not_used_for_image_extracts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Image extracts already have a structured path; the text fallback must not run."""
    from app.modules.math.schemas import MathImageExtract

    async def fake(**kwargs: object) -> None:
        raise AssertionError("text fallback must not run for image extracts")

    monkeypatch.setattr(litellm_gateway, "complete_structured", fake)
    _note, verified = await math_prompt.build_math_augmentation(
        "solve",
        _settings(),
        has_image_attachment=True,
        image_math_extract=MathImageExtract(
            lhs="2*x+3", rhs="7", variables=["x"], found=True, source_text="2x + 3 = 7"
        ),
        needs_math=True,
    )
    assert verified is not None


@pytest.mark.asyncio
async def test_image_intent_with_nondefault_domain_is_dropped() -> None:
    """OCR-derived intents obey the same whole-request audit as text extractors."""
    from app.modules.math.schemas import MathImageExtract

    note, verified = await math_prompt.build_math_augmentation(
        "Solve this over the integers",
        _settings(),
        has_image_attachment=True,
        image_math_extract=MathImageExtract(lhs="x^2", rhs="2", variables=["x"], found=True),
        needs_math=True,
    )
    assert verified is None
    assert note is not None and "Do NOT claim SymPy verification" in note


@pytest.mark.asyncio
async def test_image_source_domain_is_audited_when_caption_has_no_constraint() -> None:
    """A condition printed in the image cannot be lost by the OCR structure."""
    from app.modules.math.schemas import MathImageExtract

    note, verified = await math_prompt.build_math_augmentation(
        "Solve this",
        _settings(),
        has_image_attachment=True,
        image_math_extract=MathImageExtract(
            lhs="x^2",
            rhs="2",
            variables=["x"],
            found=True,
            source_text="x^2=2, x∈ℤ",
        ),
        needs_math=True,
    )
    assert verified is None
    assert note is not None and "Do NOT claim SymPy verification" in note


@pytest.mark.asyncio
async def test_every_independent_image_reading_is_audited() -> None:
    from app.modules.math.schemas import MathImageExtract

    note, verified = await math_prompt.build_math_augmentation(
        "Solve this",
        _settings(),
        has_image_attachment=True,
        image_math_extract=MathImageExtract(
            lhs="x^2",
            rhs="2",
            variables=["x"],
            source_text="x^2=2",
            alternate_source_text="x^2=2, x∈ℤ",
        ),
        needs_math=True,
    )
    assert verified is None
    assert note is not None and "Do NOT claim SymPy verification" in note
