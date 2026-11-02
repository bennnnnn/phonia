"""Validate solver-owned answer, arithmetic, geometry, and graph fences.

The model is asked to explain in Markdown + ``$...$``. Recall attaches
solver-owned `` ```answer `` / `` ```graph `` / `` ```geometry `` after the
stream from ``VerifiedMathBlock``. If the model still emitted a same-kind
fence, it is replaced with the canonical JSON (or answer body) so a
drifted or hallucinated number never reaches the user.

When this turn produced a canonical `` ```graph `` fence but it (or the
substituted JSON) is still sparse, we densify by re-sampling that *verified*
expression. Model-emitted geometry/graph JSON with no matching canonical
fence is stripped — schema-valid invented numbers must not ship as if
verified. Discrete point markers and vertical lines stay untouched.

After rewriting any fences the model still produced, we append canonical
fences that are missing so the client always gets the solver-owned
diagram. The verified `` ```answer `` pill lands under the reply's **Answer**
heading in place of the model's own final line (``land_answer_card``), or at
the end when the reply has no Answer section. A *different* final value in the
prose gets one correction line right above it. Every pill this module writes
carries the server's ``verified: true`` marker; a model's own answer fence
never does.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.modules.math.fence_answer import reply_asks_instead_of_answering
from app.modules.math.fence_graph import densify_sparse_graph
from app.modules.math.schemas import GraphBlockSpec
from app.modules.math.text_plot import strip_text_plots
from app.modules.math.tools.direct_counting import verified_counting_fence
from app.modules.math.unverified_note import (
    append_unverified_math_note as append_unverified_math_note,
)
from app.services.answer_check import correction_line, stated_verdict
from app.services.answer_fence import (
    ANSWER_FENCE_LANGS,
    demote_answer_body,
    land_answer_card,
    verified_answer_fence,
)
from app.services.md_fence_scan import (
    has_closed_fence,
    iter_fences,
    map_closed_fences,
    strip_closed_fences,
    strip_gfm_pipe_tables,
    strip_hand_sketch_filler,
)

if TYPE_CHECKING:
    from app.modules.math.tools import VerifiedMathBlock


# Shared 5s SymPy budget for the whole reply — bound how many fences we
# rewrite so one long message degrades per-fence instead of timing out all.
_MAX_ANSWER_FENCES = 4
_MAX_GEOMETRY_FENCES = 4
_MAX_GRAPH_FENCES = 2
_MAX_ARITHMETIC_FENCES = 1
_ANSWER_FENCE_LANGS = ANSWER_FENCE_LANGS
_CHART_ALIAS_LANGS = ("chart", "vega", "vega-lite", "plot")
_DIAGRAM_FAIL_NOTE = "\n*Could not render that diagram.*\n"
_WORKING_FAIL_NOTE = "\n*Could not render that written working.*\n"

_GEOMETRY_TYPES = frozenset(
    {
        "rectangle",
        "rect",
        "square",
        "triangle",
        "right_triangle",
        "triangle_sides",
        "circle",
        "trapezoid",
        "parallelogram",
        "sector",
    }
)
_GRAPH_TYPES = frozenset({"function", "vertical", "number_line", "trajectory", "inequality"})


def _canonical_replacement(
    raw: str,
    canonical_fence: dict[str, object] | None,
    canonical_fences: list[dict[str, object]] | None = None,
) -> str | None:
    """If a canonical fence exists for this turn and the model's fence is the
    same kind, return the canonical JSON to substitute in — the model's own
    numbers are never trusted once we have the real computed values.

    ``canonical_fences`` (from multiple tool-loop rounds) is matched by type
    so a geometry fence from round 1 isn't lost when round 2 produced a graph
    fence. The primary is searched **alongside** it, not only when it is empty:
    the other two readers of this pair (`collect_canonical_specs` and
    `_solver_fences`) already prepend the primary, and this one treating the
    list as a replacement meant a caller storing only the extras would have its
    primary silently stop matching — which is exactly what happened when a
    physics scene was added beside a trajectory graph, striking out the graph
    the reply already carried. The tool loop stores the primary in both, and a
    duplicate here is harmless: the first type match wins either way.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    fences = [fence for fence in (canonical_fence, *(canonical_fences or [])) if fence is not None]
    if not fences:
        return None
    data_type = data.get("type")
    for fence in fences:
        if data_type == fence.get("type"):
            return json.dumps(fence, separators=(",", ":"))
    # Model often emits a y=f(x) step for "graph x > 3"; replace any graph
    # fence with the verified number line.
    for fence in fences:
        if fence.get("type") == "inequality" and data_type in _GRAPH_TYPES:
            return json.dumps(fence, separators=(",", ":"))
        if fence.get("type") == "number_line" and data_type in {
            "function",
            "vertical",
            "number_line",
        }:
            return json.dumps(fence, separators=(",", ":"))
        if fence.get("type") == "trajectory" and data_type in {
            "function",
            "vertical",
            "trajectory",
        }:
            return json.dumps(fence, separators=(",", ":"))
    return None


def _graph_fence_body(spec: GraphBlockSpec) -> str:
    return f"```graph\n{json.dumps(spec.model_dump(), separators=(',', ':'))}\n```"


def _replace_unclosed_graph_fence(
    content: str,
    canonical_fence: dict[str, object] | None,
    *,
    densify: bool = True,
) -> str:
    """Replace a ```graph fence the model left unclosed (truncated mid-JSON,
    usually because it stopped copying the verified points array at EOS).

    Closed fences are handled separately. This only fires when the next
    fence marker is another opener (```python) or the message ends — so
    following prose is not swallowed into the graph body.
    """
    found = _unclosed_graph(content)
    if found is None:
        return content
    head, rest = found

    if canonical_fence is None or canonical_fence.get("type") not in {
        "function",
        "vertical",
        "number_line",
        "trajectory",
        "inequality",
    }:
        note = _DIAGRAM_FAIL_NOTE
        return head + note + rest
    try:
        parsed = GraphBlockSpec.model_validate(canonical_fence)
    except (ValidationError, TypeError):
        note = _DIAGRAM_FAIL_NOTE
        return head + note + rest
    spec = densify_sparse_graph(parsed) if densify else parsed
    suffix = rest if rest.startswith("\n") else ("\n" + rest if rest else "\n")
    return head + "\n" + _graph_fence_body(spec) + suffix


def _unclosed_graph(content: str) -> tuple[str, str] | None:
    """The text before a ```graph left open, and what follows it (from the next opener):
    in model text a later ```python opener is the model forgetting the closer."""
    for fence in iter_fences(content):
        if not fence.closed and fence.opener.info.lower().split()[:1] == ["graph"]:
            return content[: fence.start], content[fence.end :]
    return None


def replace_unclosed_graph_fence_safe(
    content: str, canonical_fence: dict[str, object] | None
) -> str:
    """SymPy-free fallback for an unclosed ```graph fence.

    Use on the ``validate_math_fences`` timeout path: the densify pass (which
    runs SymPy) was killed, but a truncated graph fence the model left at EOS
    still needs to be cleaned up so the client doesn't render a half-pasted
    points array. Closed unmatched `` ```geometry `` / `` ```graph `` fences
    are degraded the same way as ``validate_math_fences`` (P0-G), without
    densify. Substitute the verified canonical fence as-is or strip to the
    "Could not render that diagram." note. No SymPy, no sampling — safe to
    run after a solve timeout.
    """
    content = _replace_unclosed_graph_fence(content, canonical_fence, densify=False)
    return _degrade_closed_diagram_fences(content, canonical_fence)


def _degrade_closed_diagram_fences(content: str, canonical_fence: dict[str, object] | None) -> str:
    """Strip closed unmatched geometry/graph fences. No SymPy densify."""
    content = map_closed_fences(
        content,
        "geometry",
        lambda body: _replace_fence(body, "geometry", canonical_fence, densify=False),
    )
    return map_closed_fences(
        content,
        "graph",
        lambda body: _replace_fence(body, "graph", canonical_fence, densify=False),
    )


def _replace_fence(
    raw: str,
    label: str,
    canonical_fence: dict[str, object] | None,
    canonical_fences: list[dict[str, object]] | None = None,
    *,
    densify: bool = True,
) -> str:
    """Replace a model solver-owned fence with canonical JSON, or strip it.

    Schema-valid invented numbers must not ship. There is no pass-through
    path for unmatched fences.
    """
    raw = raw.strip()
    corrected = _canonical_replacement(raw, canonical_fence, canonical_fences)
    if corrected is None:
        return _WORKING_FAIL_NOTE if label == "arithmetic" else _DIAGRAM_FAIL_NOTE
    if label != "graph":
        return f"```{label}\n{corrected}\n```"
    # Densify only the verified canonical curve — never an unverified
    # model expr (that would polish a wrong function into looking true).
    try:
        parsed = GraphBlockSpec.model_validate(json.loads(corrected))
    except (json.JSONDecodeError, ValidationError, TypeError):
        return f"```{label}\n{corrected}\n```"
    densified = densify_sparse_graph(parsed) if densify else parsed
    if densified is parsed:
        return f"```graph\n{corrected}\n```"
    return _graph_fence_body(densified)


def canonical_answer_body(verified: VerifiedMathBlock | None) -> str | None:
    if verified is None:
        return None
    if verified.response_intent is not None and not verified.response_intent.reveal_answer:
        return None
    answer_only = (
        verified.response_intent is not None and verified.response_intent.mode == "answer_only"
    )
    from app.modules.math.tools.direct_arithmetic import equation_line_hides_for_answer_only

    if answer_only and equation_line_hides_for_answer_only(verified):
        # "Just the answer" is the number. The equation is the ordinary line.
        return verified.canonical_answer.strip() if verified.canonical_answer else None
    if verified.display_answer and verified.display_answer.strip():
        return verified.display_answer.strip()
    if verified.canonical_answer and verified.canonical_answer.strip():
        return verified.canonical_answer.strip()
    fences: list[dict[str, object]] = []
    if verified.canonical_fence:
        fences.append(verified.canonical_fence)
    fences.extend(verified.canonical_fences or [])
    for fence in fences:
        if fence.get("type") != "answer":
            continue
        content = fence.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def spec_fence_kind(spec: dict[str, object]) -> str | None:
    from app.modules.math.schemas.teaching import TEACHING_TYPES

    spec_type = spec.get("type")
    if spec_type == "answer":
        return "answer"
    if spec_type in TEACHING_TYPES:
        return "teach"
    if spec_type == "arithmetic":
        return "arithmetic"
    if spec_type == "fraction":
        return "arithmetic"
    if spec_type in _GEOMETRY_TYPES:
        return "geometry"
    if spec_type in _GRAPH_TYPES:
        return "graph"
    if any(key in spec for key in ("width", "height", "side", "radius", "base", "top")):
        return "geometry"
    if any(key in spec for key in ("expr", "points", "x_min", "intervals")):
        return "graph"
    return None


def _markdown_fence(kind: str, body: str) -> str:
    return f"```{kind}\n{body}\n```"


def collect_canonical_specs(verified: VerifiedMathBlock) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    seen: set[int] = set()
    for spec in [verified.canonical_fence, *(verified.canonical_fences or [])]:
        if not isinstance(spec, dict):
            continue
        marker = id(spec)
        if marker in seen:
            continue
        seen.add(marker)
        specs.append(spec)
    return specs


def _verified_includes_graph(verified: VerifiedMathBlock) -> bool:
    return any(spec_fence_kind(spec) == "graph" for spec in collect_canonical_specs(verified))


def _append_missing_canonical_fences(
    content: str, verified: VerifiedMathBlock | None, *, correct: bool = True
) -> str:
    """Attach solver-owned fences the model was told not to emit."""
    if verified is None:
        return content
    answer_body = canonical_answer_body(verified)
    # A reply that asks rather than answers has no answer to decorate, so it
    # gets no pill, no diagram and no chart — not one of the three.
    if reply_asks_instead_of_answering(content, answer_body):
        return content
    extras: list[str] = []
    correction: str | None = None
    if answer_body and correct and stated_verdict(content, answer_body) == "conflict":
        correction = correction_line(answer_body)

    specs = collect_canonical_specs(verified)
    geo = next((spec for spec in specs if spec_fence_kind(spec) == "geometry"), None)
    if geo is not None and not has_closed_fence(content, "geometry"):
        extras.append(_markdown_fence("geometry", json.dumps(geo, separators=(",", ":"))))
    graph = next((spec for spec in specs if spec_fence_kind(spec) == "graph"), None)
    if graph is not None and not has_closed_fence(content, "graph"):
        extras.append(_markdown_fence("graph", json.dumps(graph, separators=(",", ":"))))
    teaching = next((spec for spec in specs if spec_fence_kind(spec) == "teach"), None)
    answer_only = (
        verified.response_intent is not None and verified.response_intent.mode == "answer_only"
    )
    withhold = verified.response_intent is not None and not verified.response_intent.reveal_answer
    if (
        teaching is not None
        and not answer_only
        and not withhold
        and not has_closed_fence(content, "arithmetic")
    ):
        extras.append(_markdown_fence("arithmetic", json.dumps(teaching, separators=(",", ":"))))
    arithmetic = next((spec for spec in specs if spec_fence_kind(spec) == "arithmetic"), None)
    show_working = bool(
        arithmetic is not None
        and verified.response_intent is not None
        and verified.response_intent.reveal_answer
        and verified.response_intent.mode != "answer_only"
        and verified.response_intent.wants_explanation
    )
    working: str | None = None
    if show_working and arithmetic is not None and not has_closed_fence(content, "arithmetic"):
        working = _markdown_fence("arithmetic", json.dumps(arithmetic, separators=(",", ":")))

    if answer_body and any(has_closed_fence(content, lang) for lang in _ANSWER_FENCE_LANGS):
        # The model's own card, rewritten to the verified one in place.
        if correction is not None:
            content = _with_correction(content, correction)
    elif answer_body:
        # Written working, then any correction, right above the answer card.
        above = "\n\n".join(part for part in (working, correction) if part) or None
        content, working = land_answer_card(content, answer_body, above=above), None
    if working is not None:
        extras.insert(0, working)
    return _with_extras(content, extras)


def _with_extras(content: str, extras: list[str]) -> str:
    if not extras:
        return content
    stripped = content.rstrip()
    if stripped:
        return stripped + "\n\n" + "\n\n".join(extras) + "\n"
    return "\n\n".join(extras) + "\n"


def _with_correction(content: str, correction: str) -> str:
    """Put the correction line directly above the verified pill."""
    opener = next((f.start for f in iter_fences(content) if f.lang == "answer"), None)
    if opener is None:
        return content
    head = content[:opener].rstrip()
    joined = f"{head}\n\n{correction}\n\n" if head else f"{correction}\n\n"
    return joined + content[opener:]


def _replace_answer_fence(raw: str, answer_body: str | None) -> str:
    """Rewrite ```answer / ```result / ```final from SymPy, or demote to prose.

    A demoted fence keeps its value only (never a copied ``notation:`` header),
    with a trailing newline so the next fence opener stays on its own line.
    """
    if not answer_body:
        return demote_answer_body(raw)
    # The scan consumed the closer's newline; give it back so following text
    # never lands on the closing backticks.
    return verified_answer_fence(answer_body) + "\n"


def _function_call_json_to_graph_fence(raw: str) -> str:
    """Drop ``!function_call:{...}`` blobs.

    Graph calls used to be sampled into a ```graph fence from the model's
    expr, which shipped unverified curves. Canonical graphs are appended
    after rewrite instead. Parse only so a truncated blob still strips.
    """
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return ""
    return ""


def convert_function_call_text(content: str) -> str:
    """Find ``!function_call:{...}`` blobs (balanced JSON, may span lines)
    and strip each one. Canonical graph fences are appended separately."""
    marker = "!function_call:"
    out: list[str] = []
    i = 0
    while True:
        idx = content.find(marker, i)
        if idx == -1:
            out.append(content[i:])
            break
        out.append(content[i:idx])
        start = content.find("{", idx)
        if start == -1:
            i = len(content)
            break
        depth = 0
        end = start
        in_str = False
        esc = False
        for j in range(start, len(content)):
            ch = content[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
        raw = content[start:end]
        out.append(_function_call_json_to_graph_fence(raw))
        i = end
    return "".join(out)


def validate_math_fences(
    content: str, *, verified: VerifiedMathBlock | None = None, correct: bool = True
) -> str:
    """Rewrite solver-owned fences from ``verified`` and append the missing ones.

    ``correct`` adds a correction line above the card when the prose states a
    different final value; the server never corrects its own (instant) text.
    """
    answer_only = bool(
        verified is not None
        and verified.response_intent is not None
        and verified.response_intent.mode == "answer_only"
    )
    scoped_verified = (
        replace(verified, canonical_fence=None, canonical_fences=[])
        if answer_only and verified is not None
        else verified
    )
    canonical_fence = scoped_verified.canonical_fence if scoped_verified is not None else None
    canonical_fences = scoped_verified.canonical_fences if scoped_verified is not None else []
    answer_body = canonical_answer_body(verified)
    withhold_answer = bool(
        verified is not None
        and verified.response_intent is not None
        and not verified.response_intent.reveal_answer
    )
    if withhold_answer and verified is not None and verified.direct_reply:
        # A hint turn has one server-owned, answer-free payload. Replacing the
        # whole model draft—not merely its answer fence—also blocks prose,
        # accessibility text, and copied equations from leaking the result.
        return verified.direct_reply.rstrip()
    if answer_only:
        # “Answer only” means exactly that: do not let a canonical number line,
        # graph, geometry card, or model-authored diagram trail the result.
        for lang in ("arithmetic", "graph", "geometry", "simulation", *_CHART_ALIAS_LANGS):
            content = strip_closed_fences(content, lang)
    # A tool call written as text (!function_call:{...}) is stripped so unverified
    # graph JSON never ships. Canonical diagrams are appended after rewrite.
    content = convert_function_call_text(content)
    for lang in _ANSWER_FENCE_LANGS:
        content = map_closed_fences(
            content,
            lang,
            lambda body: "" if withhold_answer else _replace_answer_fence(body, answer_body),
            max_count=_MAX_ANSWER_FENCES,
            # Past the cap a model fence is still the model's: demote it, never
            # leave it standing as a card.
            leftover=lambda body: "" if withhold_answer else demote_answer_body(body),
        )
    content = map_closed_fences(
        content,
        "arithmetic",
        lambda body: (
            verified_counting_fence(body, verified)
            or (
                _replace_fence(body, "arithmetic", canonical_fence, canonical_fences)
                if verified is not None
                and verified.response_intent is not None
                and verified.response_intent.reveal_answer
                and verified.response_intent.wants_explanation
                else ""
            )
        ),
        max_count=_MAX_ARITHMETIC_FENCES,
        leftover=lambda _body: _WORKING_FAIL_NOTE,
    )
    content = map_closed_fences(
        content,
        "geometry",
        lambda body: _replace_fence(
            body,
            "geometry",
            canonical_fence,
            canonical_fences,
        ),
        max_count=_MAX_GEOMETRY_FENCES,
        leftover=lambda _body: _DIAGRAM_FAIL_NOTE,
    )
    content = map_closed_fences(
        content,
        "graph",
        lambda body: _replace_fence(
            body,
            "graph",
            canonical_fence,
            canonical_fences,
        ),
        max_count=_MAX_GRAPH_FENCES,
        leftover=lambda _body: _DIAGRAM_FAIL_NOTE,
    )
    # A ```graph fence the model truncated mid-JSON (stopped copying the
    # verified points at EOS) is left unclosed. Swap it for the verified
    # canonical fence so the renderer gets a complete spec.
    content = _replace_unclosed_graph_fence(content, canonical_fence)
    # Vega ```chart is a different product from a verified function plot.
    # Drop the model's chart when we already own a ```graph fence.
    if verified is not None and _verified_includes_graph(verified):
        for lang in _CHART_ALIAS_LANGS:
            content = strip_closed_fences(content, lang)
        content = strip_closed_fences(content, "mermaid")
        content = strip_gfm_pipe_tables(content)
        content = strip_hand_sketch_filler(content)
        content = strip_text_plots(content)
    return _append_missing_canonical_fences(content, scoped_verified, correct=correct)


_FENCE_VALIDATE_MARKERS = (
    "```answer",
    "```result",
    "```final",
    "```graph",
    "```geometry",
    "```arithmetic",
    "```math",
)


def needs_math_fence_validate(content: str, verified: VerifiedMathBlock | None) -> bool:
    """Skip the SymPy pool when the reply has nothing for this rewriter."""
    if verified is not None:
        return True
    lower = content.lower()
    return any(marker in lower for marker in _FENCE_VALIDATE_MARKERS)


def validate_math_fences_worker(
    content: str, verified: VerifiedMathBlock | None = None, correct: bool = True
) -> str:
    """Picklable entry for ``app.core.sympy_executor.run_sympy`` (positional args only)."""
    return validate_math_fences(content, verified=verified, correct=correct)
