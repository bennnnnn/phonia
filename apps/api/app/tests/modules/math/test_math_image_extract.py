import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.modules.math import image_extract as mie
from app.modules.math.schemas import MathImageExtract
from app.modules.math.tools import needs_symbolic_math
from app.services.subject_scan import MATH_CAMERA_PROMPT


def test_camera_math_display_text():
    eq = MathImageExtract(kind="equation", lhs="2*x+3", rhs="7", found=True)
    assert mie.camera_math_display_text(eq) == "2*x+3 = 7"
    system = MathImageExtract(
        kind="system",
        lhs="x+y",
        rhs="5",
        equations=[("x+y", "5"), ("x-y", "1")],
        found=True,
    )
    assert mie.camera_math_display_text(system) == "x+y = 5\nx-y = 1"
    calc = MathImageExtract(kind="calculus", operation="differentiate", expr="x**2", found=True)
    assert mie.camera_math_display_text(calc) == "differentiate x**2"


def test_camera_math_user_suffix_omits_structured_kinds():
    graph = MathImageExtract(kind="graph", expr="x**2", found=True)
    assert mie.camera_math_user_suffix(graph) is None
    calc = MathImageExtract(kind="calculus", operation="differentiate", expr="x**2", found=True)
    assert mie.camera_math_user_suffix(calc) is None
    rect = MathImageExtract(kind="rectangle", width=8, height=5, found=True)
    assert mie.camera_math_user_suffix(rect) is None


def test_camera_math_user_suffix_keeps_equations():
    eq = MathImageExtract(kind="equation", lhs="2*x+3", rhs="7", found=True)
    assert mie.camera_math_user_suffix(eq) == "Solve: 2*x+3 = 7"
    ineq = MathImageExtract(kind="inequality", lhs="x**2-1", rhs="0", comparator=">", found=True)
    assert mie.camera_math_user_suffix(ineq) == "Solve: x**2-1 > 0"


def test_needs_symbolic_math_for_camera_prompt():
    assert needs_symbolic_math(MATH_CAMERA_PROMPT, has_image_attachment=True)
    assert not needs_symbolic_math(MATH_CAMERA_PROMPT, has_image_attachment=False)


@pytest.mark.asyncio
async def test_extract_equation_mock_mode():
    settings = Settings()
    settings.mock_llm_enabled = True
    settings.openrouter_api_key = ""
    result = await mie.extract_equation_from_image(
        settings, content_type="image/jpeg", data=b"fake"
    )
    assert result is not None
    assert result.lhs == "2*x+3"
    assert result.rhs == "7"


@pytest.mark.asyncio
async def test_extract_equation_empty_bytes():
    result = await mie.extract_equation_from_image(Settings(), content_type="image/jpeg", data=b"")
    assert result is None


def test_math_image_extract_schema():
    parsed = MathImageExtract.model_validate(
        {"lhs": "x**2", "rhs": "4", "variables": ["x"], "found": True}
    )
    assert parsed.lhs == "x**2"


@pytest.mark.asyncio
async def test_extract_equation_uses_dedicated_ocr_timeout_not_solve_timeout():
    """BUG FIX: this call used to reuse stem_solve_timeout_seconds — a budget
    documented for local, synchronous SymPy work — for a network vision-chat
    call. A real OCR round trip taking longer than the (much shorter) solve
    budget but well within a reasonable network timeout used to be cut off
    early. Must use the dedicated math_image_extract_timeout_seconds instead."""
    settings = Settings(
        stem_solve_timeout_seconds=0.05,
        math_image_extract_timeout_seconds=2.0,
        mock_llm_enabled=False,
        openrouter_api_key="test-key",
        mathpix_enabled=False,
    )

    async def _slow_completion(**_kwargs):
        await asyncio.sleep(0.2)
        message = MagicMock()
        message.content = '{"lhs":"x","rhs":"1","variables":["x"],"found":true,"source_text":"x=1"}'
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        return response

    with patch("app.gateways.litellm_gateway.acompletion", AsyncMock(side_effect=_slow_completion)):
        result = await mie.extract_equation_from_image(
            settings, content_type="image/jpeg", data=b"fake"
        )

    assert result is not None
    assert result.lhs == "x"
    assert result.rhs == "1"


def _fake_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    response = MagicMock()
    response.choices = [MagicMock(message=message)]
    return response


def _real_path_settings() -> Settings:
    return Settings(
        mock_llm_enabled=False,
        openrouter_api_key="test-key",
        mathpix_enabled=False,
        mathpix_app_id="",
        mathpix_app_key="",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_content",
    [
        '{"lhs":"2*x+3","rhs":"7","variables":["x"],"found":true,"source_text":"2*x+3=7"}',
        # Markdown-fenced with a "json" language tag — real vision models
        # routinely wrap JSON in a fence despite being asked for raw JSON.
        '```json\n{"lhs":"2*x+3","rhs":"7","variables":["x"],"found":true,'
        '"source_text":"2*x+3=7"}\n```',
        # Fenced without a language tag.
        '```\n{"lhs":"2*x+3","rhs":"7","variables":["x"],"found":true,'
        '"source_text":"2*x+3=7"}\n```',
    ],
)
async def test_extract_equation_parses_well_formed_json(raw_content: str):
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_fake_response(raw_content)),
    ):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is not None
    assert result.lhs == "2*x+3"
    assert result.rhs == "7"
    assert result.variables == ["x"]


@pytest.mark.asyncio
async def test_extract_equation_found_false_returns_none():
    raw = '{"lhs":"0","rhs":"0","variables":["x"],"found":false}'
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_fake_response(raw)),
    ):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_content",
    [
        "not json at all",
        '{"lhs": "2*x", "rhs": }',  # malformed JSON
        "",
    ],
)
async def test_extract_equation_malformed_json_returns_none(raw_content: str):
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_fake_response(raw_content)),
    ):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is None


@pytest.mark.asyncio
async def test_extract_equation_bad_json_is_read_again_by_the_backup_photo_model():
    """V10.2: a malformed reply is asked once more of the other photo model."""
    good = '{"lhs":"2*x+3","rhs":"7","variables":["x"],"found":true,"source_text":"2*x+3=7"}'
    completion = AsyncMock(side_effect=[_fake_response("not json {{"), _fake_response(good)])
    with patch("app.gateways.litellm_gateway.acompletion", completion):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is not None and result.lhs == "2*x+3"
    models = [call.kwargs["model"] for call in completion.await_args_list]
    assert models == ["openrouter/qwen/qwen3.7-flash", "openrouter/z-ai/glm-5.3-flash"]


@pytest.mark.asyncio
async def test_extract_equation_no_problem_on_the_photo_is_not_retried():
    raw = '{"lhs":"0","rhs":"0","variables":["x"],"found":false}'
    completion = AsyncMock(return_value=_fake_response(raw))
    with patch("app.gateways.litellm_gateway.acompletion", completion):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is None
    completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_equation_pydantic_validation_failure_returns_none():
    # Missing lhs/rhs (defaults are placeholder "0") with found=true is treated
    # as not found — same outcome as the old required-field validation failure.
    raw = '{"variables":["x"],"found":true}'
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_fake_response(raw)),
    ):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is None


@pytest.mark.asyncio
async def test_extract_equation_unwraps_single_element_list():
    """Models sometimes return [{...}] instead of {...}; accept that shape."""
    raw = '[{"lhs":"x^2","rhs":"5","variables":["x"],"found":true,"source_text":"x^2=5"}]'
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_fake_response(raw)),
    ):
        result = await mie.extract_equation_from_image(
            _real_path_settings(), content_type="image/jpeg", data=b"fake"
        )
    assert result is not None
    assert result.lhs == "x^2"
    assert result.rhs == "5"
    assert result.found is True


@pytest.mark.asyncio
async def test_extract_equation_real_timeout_returns_none():
    """Distinct from test_extract_equation_uses_dedicated_ocr_timeout_not_solve_timeout
    (which proves the RIGHT budget is used) — this proves the timeout
    actually fires and degrades gracefully when the call genuinely overruns
    even the dedicated OCR budget."""
    settings = Settings(
        math_image_extract_timeout_seconds=0.05,
        mock_llm_enabled=False,
        openrouter_api_key="test-key",
    )

    async def _hangs(**_kwargs):
        await asyncio.sleep(5)
        raise AssertionError("should have been cancelled by the timeout")

    with patch("app.gateways.litellm_gateway.acompletion", side_effect=_hangs):
        result = await mie.extract_equation_from_image(
            settings, content_type="image/jpeg", data=b"fake"
        )
    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lhs", "rhs"),
    [
        pytest.param("f(x,2)", "7", id="comma"),
        pytest.param("2×x+3", "7", id="unicode-times"),
        pytest.param("|x-3|", "5", id="abs-bars"),
    ],
)
async def test_augment_prompt_messages_image_math_extract_survives_ocr_chars(
    lhs: str, rhs: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG FIX (Phase B item 6): the vision-extracted equation used to be
    discarded after stringifying to "lhs = rhs" free text, which was then
    re-parsed by try_extract_equations_from_text's restricted
    character-class regex ([0-9a-zA-Z+\\-*/().\\s^**]) — silently mangling
    or dropping commas, unicode operators, and abs-value bars a real
    photographed equation can contain. Passing the Pydantic-validated
    MathImageExtract straight through via the new image_math_extract
    parameter must produce a MathIntent with the exact extracted lhs/rhs,
    bypassing that reparse entirely."""
    from unittest.mock import AsyncMock

    from app.core.config import Settings
    from app.modules.math.schemas import MathIntent
    from app.modules.math.tools import VerifiedMathBlock
    from app.tests.modules.math.prompt_support import augment_prompt_messages

    settings = Settings(math_tools_enabled=True)
    # The page as read: every production extract carries it, and its equation is held to it.
    extract = MathImageExtract(
        lhs=lhs, rhs=rhs, variables=["x"], found=True, source_text=f"{lhs} = {rhs}"
    )
    user_content = f"Solve the math problem in this image step by step.\n\nSolve: {lhs} = {rhs}"
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": user_content},
    ]

    captured: dict[str, MathIntent] = {}

    async def _fake_build(intent: MathIntent, _settings: Settings) -> VerifiedMathBlock:
        captured["intent"] = intent
        return VerifiedMathBlock(text="stub")

    # This test is about the reparse; the page check (``image_intent_on_the_page``, which
    # cannot read "f(x,2)") has its own tests in test_math_model_readings.py.
    from app.modules.math.tools import prompt as math_prompt

    monkeypatch.setattr(math_prompt, "image_intent_on_the_page", lambda *_args: True)
    with patch(
        "app.modules.math.tools._build_verified_block_async",
        AsyncMock(side_effect=_fake_build),
    ):
        _, verified = await augment_prompt_messages(
            messages,
            user_content,
            settings,
            has_image_attachment=True,
            image_math_extract=extract,
        )

    assert verified is not None
    assert captured["intent"].kind == "equation"
    assert captured["intent"].lhs == lhs
    assert captured["intent"].rhs == rhs


@pytest.mark.asyncio
async def test_augment_prompt_messages_without_image_math_extract_mangles_ocr_text() -> None:
    """Characterizes the bug image_math_extract fixes: without it, the same
    stringified OCR text falls through to the free-text regex path, which
    corrupts a comma-containing equation (comma isn't in the extraction
    regex's character class, so it only matches the tail after the comma)."""
    from unittest.mock import AsyncMock

    from app.core.config import Settings
    from app.modules.math.schemas import MathIntent
    from app.modules.math.tools import VerifiedMathBlock
    from app.tests.modules.math.prompt_support import augment_prompt_messages

    settings = Settings(math_tools_enabled=True)
    user_content = "Solve the math problem in this image step by step.\n\nSolve: f(x,2) = 7"
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": user_content},
    ]

    captured: dict[str, MathIntent] = {}

    async def _fake_build(intent: MathIntent, _settings: Settings) -> VerifiedMathBlock:
        captured["intent"] = intent
        return VerifiedMathBlock(text="stub")

    with patch(
        "app.modules.math.tools._build_verified_block_async",
        AsyncMock(side_effect=_fake_build),
    ):
        await augment_prompt_messages(
            messages,
            user_content,
            settings,
            has_image_attachment=True,
            image_math_extract=None,
        )

    assert captured["intent"].lhs != "f(x,2)"


@pytest.mark.asyncio
async def test_extract_equation_failure_logs_at_warning_not_debug(caplog):
    """BUG FIX: failures here used to log at DEBUG, so a real OCR outage
    (bad vision-model response, network failure, timeout) produced no signal
    in prod logs at the default level. The vision call now lives in the
    litellm gateway (vision_completion), which owns the provider-error log —
    so the WARNING signal must surface there, not in the service logger."""
    settings = Settings(
        mock_llm_enabled=False, openrouter_api_key="test-key", mathpix_enabled=False
    )

    with (
        patch(
            "app.gateways.litellm_gateway.acompletion",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        caplog.at_level(logging.WARNING, logger="app.gateways.litellm_gateway"),
    ):
        result = await mie.extract_equation_from_image(
            settings, content_type="image/jpeg", data=b"fake"
        )

    assert result is None
    assert any(
        "Vision LLM" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )
