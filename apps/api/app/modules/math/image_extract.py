"""Extract an equation from an image via the photo model (best-effort).

A reply that is not valid JSON for ``MathImageExtract`` is asked once more of the
backup photo model; a photo with no problem on it is an answer, not a retry.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.gateways import litellm_gateway, mock_llm
from app.gateways.model_output import parse_model_json
from app.models.model_catalog import vision_alias, vision_backup_alias
from app.modules.math.schemas import MathImageExtract

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Extract the primary math problem from this image as a single JSON object "
    "(not an array). Always include found (boolean) and variables (array). "
    "When found=true, always include source_text as an exact transcription of "
    "the complete visible problem, including every domain, condition, and request. "
    "Use ASCII math (* / ** for multiply/divide/power). Write logarithms as printed: "
    "log(x) is base 10, ln(x) is the natural log, log_2(x) has base 2. Never invent dimensions "
    "or freehand diagrams — only extract numbers/expressions printed on the page. "
    "kind is one of: equation, system, inequality, calculus, limit, graph, "
    "rectangle, circle, triangle_sides, statistics. "
    "Equation: fill lhs, rhs. "
    'Example: {"kind":"equation","lhs":"2*x+3","rhs":"7","variables":["x"],'
    '"found":true}. '
    "System: also fill equations as [lhs,rhs] pairs for EVERY equation "
    "(including the first) and set lhs/rhs to the first pair. "
    'Example: {"kind":"system","lhs":"x+y","rhs":"5",'
    '"equations":[["x+y","5"],["x-y","1"]],"variables":["x","y"],"found":true}. '
    'Inequality: comparator one of "<", ">", "<=", ">=". '
    'Example: {"kind":"inequality","lhs":"x**2-1","rhs":"0","comparator":">",'
    '"variables":["x"],"found":true}. '
    "Calculus: fill expr plus operation "
    "(simplify|differentiate|integrate|factor|expand). For a definite integral "
    "also fill integral_lower and integral_upper (both required; omit both "
    "for indefinite). "
    'Example: {"kind":"calculus","operation":"differentiate","expr":"x**2",'
    '"variables":["x"],"found":true}. '
    'Definite: {"kind":"calculus","operation":"integrate","expr":"x**2",'
    '"integral_lower":"0","integral_upper":"1","variables":["x"],"found":true}. '
    "Limit: fill expr and limit_point (number or infinity). "
    'Example: {"kind":"limit","expr":"sin(x)/x","limit_point":"0",'
    '"variables":["x"],"found":true}. '
    "Graph: fill expr to plot as y=f(x). "
    'Example: {"kind":"graph","expr":"x**2","variables":["x"],"found":true}. '
    "Rectangle/circle: fill printed width+height or radius and optional unit. "
    'Example: {"kind":"rectangle","width":8,"height":5,"unit":"cm","found":true}. '
    "Triangle with three printed side lengths (SSS): fill tri_a, tri_b, tri_c. "
    'Example: {"kind":"triangle_sides","tri_a":3,"tri_b":4,"tri_c":5,'
    '"unit":"cm","found":true}. '
    "Statistics on a printed data list: fill stats_numbers and stats_op "
    "(mean|median|mode|variance|stdev). "
    'Example: {"kind":"statistics","stats_op":"mean","stats_numbers":[1,3,5,7],'
    '"found":true}. '
    'If nothing extractable, set found=false and use lhs/rhs of "0".'
)

_SOLVE_KINDS = frozenset({"equation", "system", "inequality"})
_OCR_HINT_MAX = 2000


def camera_math_user_suffix(extracted: MathImageExtract) -> str | None:
    """Extra user-text for the model. Structured kinds must not inject
    ``Solve: 0 = 0`` from unused lhs/rhs defaults."""
    if not extracted.found:
        return None
    if extracted.kind not in _SOLVE_KINDS:
        return None
    if extracted.kind == "inequality":
        cmp_op = extracted.comparator if extracted.comparator else "="
        return f"Solve: {extracted.lhs} {cmp_op} {extracted.rhs}"
    if extracted.kind == "system" and extracted.equations:
        lines = "\n".join(f"{lhs} = {rhs}" for lhs, rhs in extracted.equations)
        return f"Solve:\n{lines}"
    return f"Solve: {extracted.lhs} = {extracted.rhs}"


def camera_math_display_text(extracted: MathImageExtract) -> str | None:
    """Human-readable OCR read-back for the scanner preview."""
    if not extracted.found:
        return None
    kind = extracted.kind
    if kind == "inequality":
        cmp_op = extracted.comparator if extracted.comparator else "="
        return f"{extracted.lhs} {cmp_op} {extracted.rhs}"
    if kind == "system" and extracted.equations:
        return "\n".join(f"{lhs} = {rhs}" for lhs, rhs in extracted.equations)
    if kind == "calculus" and extracted.expr and extracted.operation:
        op = extracted.operation
        if op == "integrate" and extracted.integral_lower and extracted.integral_upper:
            return (
                f"integrate {extracted.expr} from {extracted.integral_lower} "
                f"to {extracted.integral_upper}"
            )
        return f"{op} {extracted.expr}"
    if kind == "limit" and extracted.expr:
        return f"limit {extracted.expr} as x -> {extracted.limit_point}"
    if kind == "graph" and extracted.expr:
        return f"y = {extracted.expr}"
    if kind == "rectangle" and extracted.width is not None and extracted.height is not None:
        return f"rectangle {extracted.width} x {extracted.height} {extracted.unit}"
    if kind == "circle" and extracted.radius is not None:
        return f"circle radius {extracted.radius} {extracted.unit}"
    if (
        kind == "triangle_sides"
        and extracted.tri_a is not None
        and extracted.tri_b is not None
        and extracted.tri_c is not None
    ):
        return (
            f"triangle sides {extracted.tri_a}, {extracted.tri_b}, "
            f"{extracted.tri_c} {extracted.unit}"
        )
    if kind == "statistics" and extracted.stats_numbers and extracted.stats_op:
        nums = ", ".join(str(n) for n in extracted.stats_numbers)
        return f"{extracted.stats_op} of {nums}"
    if extracted.lhs.strip() not in ("", "0") or extracted.rhs.strip() not in ("", "0"):
        return f"{extracted.lhs} = {extracted.rhs}"
    return None


def _extract_prompt(ocr_hint: str | None) -> str:
    if not ocr_hint:
        return _EXTRACT_PROMPT
    hint = ocr_hint.strip()
    if len(hint) > _OCR_HINT_MAX:
        hint = hint[:_OCR_HINT_MAX]
    return (
        f"{_EXTRACT_PROMPT} An OCR engine transcribed this image as:\n{hint}\n"
        "Treat that transcription as a hint; prefer the image if they disagree."
    )


async def vision_extract_equation(
    settings: Settings,
    *,
    content_type: str,
    data: bytes,
    ocr_hint: str | None = None,
    timeout_seconds: float | None = None,
) -> MathImageExtract | None:
    """Gemini/vision-chat structured extract. Never raises into the chat path.

    ``timeout_seconds`` (default ``math_image_extract_timeout_seconds``) is
    the budget for the whole extract: the backup model's retry gets what the
    first attempt left, never a fresh budget.
    """
    if not data:
        return None
    if mock_llm.should_mock_llm(settings):
        return MathImageExtract(
            lhs="2*x+3",
            rhs="7",
            variables=["x"],
            found=True,
            source_text="2*x+3=7",
        )

    try:
        mime = content_type.split(";")[0].strip() or "image/jpeg"
        encoded = base64.standard_b64encode(data).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _extract_prompt(ocr_hint)},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}"},
                    },
                ],
            }
        ]
        budget = (
            settings.math_image_extract_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        for alias in (vision_alias(), vision_backup_alias()):
            left = deadline - loop.time()
            if left <= 0:
                return None
            response = await litellm_gateway.vision_completion(
                settings=settings,
                model_alias=alias,
                messages=messages,
                max_tokens=384,
                response_format={"type": "json_object"},
                timeout_seconds=left,
            )
            if response is None:
                return None
            try:
                return _read_extract(response)
            except (ValueError, ValidationError):
                logger.warning("math image extract returned invalid JSON alias=%s", alias)
        return None
    except Exception:
        # Was logger.debug — silently swallowed a real OCR outage (bad
        # vision-model response, network failure, timeout) with no signal
        # in prod logs at the default level.
        logger.warning("math image extract failed", exc_info=True)
        return None


def _read_extract(response: Any) -> MathImageExtract | None:
    """The equation in a photo reply, None when it holds none; raises on malformed JSON."""
    # The shared reader escapes the LaTeX an exact transcription holds (``\frac`` read as
    # a form feed, ``\sqrt`` failed the extract over to the backup model).
    data_obj = parse_model_json(response.choices[0].message.content or "{}")
    # Vision models sometimes wrap the object in a one-element array.
    if isinstance(data_obj, list):
        if len(data_obj) != 1 or not isinstance(data_obj[0], dict):
            raise ValueError("not one extract object")
        data_obj = data_obj[0]
    parsed = MathImageExtract.model_validate(data_obj)
    if not parsed.found:
        return None
    if not (parsed.source_text or "").strip():
        # The exact transcription is the evidence used to audit whether
        # the structured JSON dropped a printed restriction or subtask.
        return None
    return parsed


async def extract_equation_from_image(
    settings: Settings,
    *,
    content_type: str,
    data: bytes,
) -> MathImageExtract | None:
    """Best-effort extract — Mathpix when configured, else vision-chat."""
    from app.modules.math.ocr import extract_math_from_image

    result = await extract_math_from_image(settings, content_type=content_type, data=data)
    return result.extract
