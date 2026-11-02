"""Physics-owned reconciliation of answer, trajectory, and simulation fences.

On a verified turn the model's own result fences are dropped, the solver's
card (marked ``verified: true``) lands under the reply's **Answer** heading in
place of the model's final line, and the scene is appended. A reply that answers
and then offers more ("Want the max height too?") keeps both; only a reply that
asks instead of stating any result goes without. A final value in the prose
that differs from the verified one gets one correction line above the card.
"""

from __future__ import annotations

import json
import logging
import re

from app.modules.physics.part_answers import land_one_part_card, land_part_cards, parts_conflict
from app.modules.physics.schemas.simulation import SIMULATION_SPEC_TYPES
from app.services.answer_check import asks_without_answering, correction_line, stated_verdict
from app.services.answer_fence import ANSWER_FENCE_LANGS, land_answer_card
from app.services.md_fence_scan import (
    block_end,
    close_unclosed_fences,
    iter_fences,
    strip_closed_fences,
)
from app.services.part_answer_cards import land_part_answer_cards
from app.services.solving import VerifiedPhysicsBlock
from app.services.workout import as_formula_heading

logger = logging.getLogger(__name__)

_PICTURE_FENCE_LANGS = ("graph", "simulation", "geometry")
_DIAGRAM_FAILED = "*Could not render that diagram.*"
# A plain block may hold a sketch; a tagged one (python, math) never does.
_PLAIN_FENCE_LANGS = frozenset({"", "text", "txt", "plaintext", "ascii"})
# The model's own diagram of the situation ("graph TD Battery --> R1"): the solver's
# picture draws it, so a second, rougher one goes. A user who asked for a flowchart
# or a Mermaid diagram keeps theirs.
_MODEL_DIAGRAM_LANGS = frozenset({"mermaid"})
_ASKED_FOR_DIAGRAM = re.compile(
    r"\b(?:flow[\s-]?charts?|mermaid|sequence diagram|mind[\s-]?maps?|state diagram)\b",
    re.IGNORECASE,
)
# Box-drawing lines, arrows and blocks, or a run of slashes, bars and dashes.
_DRAWN = re.compile(r"[\u2190-\u21ff\u2500-\u257f\u25a0-\u25ff]|[-_|/\\]{3,}|[/\\]\s*$")
# "The diagram is drawn under this reply": where the app puts the picture, not the
# lesson's words (2026-10-30). The picture is simply below.
_DRAWN_UNDER_REPLY = re.compile(
    r"\b(is|are)\s+drawn\s+(?:under|below|beneath)\s+(?:this|the|my)\s+(?:reply|answer|message)",
    re.IGNORECASE,
)


def _has_picture_fence(content: str) -> bool:
    return any(fence.lang in _PICTURE_FENCE_LANGS for fence in iter_fences(content))


def _without_model_result_fences(content: str) -> str:
    """The prose: the model's own cards and pictures go; only the solver's ship."""
    for language in (*ANSWER_FENCE_LANGS, *_PICTURE_FENCE_LANGS):
        content = strip_closed_fences(content, language)
    return content.strip()


def _canonical_specs(verified: VerifiedPhysicsBlock) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for spec in (verified.canonical_fence, *verified.canonical_fences):
        if spec is not None and spec not in specs:
            specs.append(spec)
    return specs


def _scene_fences(verified: VerifiedPhysicsBlock) -> list[str]:
    """The solver's pictures: its sampled ```graph and ```simulation scenes."""
    fences: list[str] = []
    for spec in _canonical_specs(verified):
        spec_type = spec.get("type")
        if spec_type == "answer":
            continue
        language = "simulation" if spec_type in SIMULATION_SPEC_TYPES else "graph"
        fences.append(f"```{language}\n{json.dumps(spec, separators=(',', ':'))}\n```")
    return fences


def solver_cards(verified: VerifiedPhysicsBlock) -> tuple[str, ...]:
    """The fences physics writes for the block: its answer card (each part's, for a
    solve in parts) and its pictures."""
    answers = [part.display_answer for part in verified.physics_parts]
    if len(answers) < 2:
        answers = [(verified.display_answer or verified.canonical_answer or "").strip()]
    cards = [f"```answer\n{answer}\n```" for answer in answers if answer]
    return (*cards, *_scene_fences(verified))


def validate_physics_fences(
    content: str,
    *,
    verified: VerifiedPhysicsBlock | None = None,
    correct: bool = True,
    user_text: str = "",
) -> str:
    """Drop model-authored result fences and append only solver-owned data.

    ``correct`` adds a correction line above the card when the prose states a
    different final value; the server never corrects its own (instant) text.
    ``user_text`` is the request: a flowchart it asked for survives the picture.
    """
    had_visual_fence = _has_picture_fence(content)
    cleaned = _without_model_result_fences(content)
    if verified is None:
        if had_visual_fence and not cleaned:
            return _DIAGRAM_FAILED
        return cleaned
    answer = (verified.display_answer or verified.canonical_answer or "").strip()
    # A question in parts: each part's card under its own Answer heading. A reply whose
    # part states another value is left as written, with no card claiming either.
    part_cards = [part.display_answer for part in verified.physics_parts]
    if len(part_cards) > 1 and parts_conflict(cleaned, part_cards):
        return cleaned
    by_part = land_part_cards(cleaned, part_cards)
    if by_part is None and answer and len(verified.physics_parts) < 2:
        by_part = land_one_part_card(cleaned, answer)
        # The parts the server did not solve get their own card, without the check.
        if by_part is not None:
            by_part = land_part_answer_cards(by_part) or by_part
    if by_part is not None:
        cleaned, answer = by_part, ""
    # The law's own heading heads inputs, like **Formula**: its equations are no result.
    read = as_formula_heading(cleaned)
    if answer and _asks_instead_of_answering(read, answer):
        return cleaned
    if answer:
        conflict = correct and stated_verdict(read, answer) == "conflict"
        cleaned = land_answer_card(
            cleaned, answer, above=correction_line(answer) if conflict else None
        )
    extras = _scene_fences(verified)
    if not extras:
        return cleaned
    keep_diagrams = _ASKED_FOR_DIAGRAM.search(user_text) is not None
    return _with_pictures(_without_model_drawings(cleaned, keep_diagrams), extras)


def _without_model_drawings(text: str, keep_diagrams: bool) -> str:
    """The solver's picture replaces the model's own drawing of the same thing: a box
    in ASCII art reads as broken rows of symbols on the phone, and a Mermaid "circuit"
    above the real schematic is a second, wrong one."""
    drawings = [
        fence
        for fence in iter_fences(text)
        if (fence.lang in _MODEL_DIAGRAM_LANGS and not keep_diagrams)
        or (
            fence.lang in _PLAIN_FENCE_LANGS
            and sum(
                bool(_DRAWN.search(row))
                for row in text[fence.body_start : fence.body_end].split("\n")
            )
            >= 2
        )
    ]
    for fence in reversed(drawings):
        text = text[: fence.start] + text[fence.end :]
    return re.sub(r"\n{3,}", "\n\n", text).strip() if drawings else text


# "### Joke": a later request's section, after the one the solve answered.
_LATER_SECTION = re.compile(r"^#{2,3}\s+\S", re.MULTILINE)


def _with_pictures(text: str, pictures: list[str]) -> str:
    """The solve's pictures under its last answer card when another request's section
    follows it ("…, and also tell me a joke": the graph under the joke read as the
    joke's); otherwise at the end, as ever."""
    if pictures:
        text = _DRAWN_UNDER_REPLY.sub(r"\1 shown below", text)
    cards = [fence for fence in iter_fences(text) if fence.closed and fence.lang == "answer"]
    end = block_end(text, cards[-1]) if cards else -1
    if pictures and end >= 0 and _LATER_SECTION.search(text, end):
        return f"{text[:end]}\n\n" + "\n\n".join(pictures) + text[end:]
    return "\n\n".join(part for part in (text, *pictures) if part).strip()


def _asks_instead_of_answering(content: str, answer: str) -> bool:
    """A question and no result of its own: no card, no scene under it.

    Any stated final value, right or wrong, means the reply answered; a
    follow-up offer after it does not take the card away.
    """
    numeric = asks_without_answering(content, answer)
    if numeric is not None:
        return numeric
    if not any(line.rstrip("*_`~ \t").endswith("?") for line in content.splitlines()):
        return False
    normalized_content = re.sub(r"\s+", " ", content.lower())
    normalized_answer = re.sub(r"\s+", " ", answer.lower())
    return normalized_answer not in normalized_content


def replace_unclosed_physics_fences_safe(
    content: str,
    verified: VerifiedPhysicsBlock | None,
) -> str:
    """Physics-owned, no-solver fallback after finalization fails.

    Close a truncated rich fence, then make one ordinary canonical pass.  If
    even that fails, strip every physics/result fence and keep only prose;
    never send a physics turn through math's graph recovery semantics.
    """
    closed = close_unclosed_fences(content)
    try:
        return validate_physics_fences(closed, verified=verified)
    except Exception:
        logger.warning("physics fence finalization failed; keeping prose only", exc_info=True)
        cleaned = _without_model_result_fences(closed)
        return cleaned or (_DIAGRAM_FAILED if _has_picture_fence(closed) else "")
