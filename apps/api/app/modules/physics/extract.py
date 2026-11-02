"""Stable public facade for physics detection and extraction."""

from __future__ import annotations

import re
from functools import lru_cache

from app.core.readings import reading
from app.modules.physics.registry import (
    PHYSICS_CUE_RES,
    PHYSICS_CUES,
    PHYSICS_EXTRACTORS,
    has_supported_physics_cue,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.number_text import fold_scientific
from app.services.symbolic_text import (
    _MAX_PHYSICS_REQUEST,
    _MAX_SUBJECT_TEXT,
    normalize_symbolic_request,
)
from app.services.text_normalize import cap_text_head_tail

__all__ = [
    "PHYSICS_CUES",
    "PHYSICS_CUE_RES",
    "PHYSICS_EXTRACTORS",
    "extract_physics_intent",
    "has_supported_physics_cue",
    "needs_physics",
]

_DIGIT_FREE_PHYSICS_RE = re.compile(
    r"\b(?:escape velocity|escape speed|orbital velocity|orbital speed|"
    r"surface gravity|gravitational field strength|hawking temperature|"
    r"hawking power|hawking luminosity|acceleration due to gravity|"
    r"gravitational acceleration)\b"
    r"[^.?!]{0,60}?\b(?:earth|moon|mars|jupiter|sun)\b"
    r"|\b(?:earth|moon|mars|jupiter|sun)\b[^.?!]{0,60}?"
    r"\b(?:escape velocity|escape speed|orbital velocity|orbital speed|"
    r"surface gravity|gravitational field strength|hawking temperature|"
    r"hawking power|hawking luminosity|acceleration due to gravity|"
    r"gravitational acceleration)\b"
    r"|\bpair[- ]production\b[^.?!]{0,80}?\b(?:electron|proton|neutron|positron)\b"
    r"|\b(?:electron|proton|neutron|positron)\b[^.?!]{0,80}?\bpair[- ]production\b",
    re.IGNORECASE,
)

# Recognized as physics, then left unverified. Closed school templates that
# now have a solver stay off this list, including Kirchhoff, Gauss, Faraday,
# inductors, RL, AC, Poiseuille, the quantum oscillator's levels and the
# Rydberg formula.
_ADVANCED_PHYSICS_RE = re.compile(
    r"\b(?:schr[oö]dinger|hamilton(?:ian|'s equations?)?|lagrang(?:ian|e)|"
    r"maxwell(?:'s)? equations?|general relativity|schwarzschild|"
    r"quantum harmonic oscillator|wave ?function|probability density|"
    r"diffraction grating|capillary rise|transformer|nuclear reaction|"
    r"binding energy|mass defect|rydberg|blackbody distribution|"
    r"planck(?:'s)? distribution|gear ratio)\b",
    re.IGNORECASE,
)


# A reminder or a to-do that names a battery or a bulb: "remind me to buy a 9V
# battery tomorrow" is an errand, not a circuit. "remind me how ..." still asks.
_ERRAND_RE = re.compile(
    r"^\s*(?:(?:please|hey|ok|okay|can\s+you|could\s+you)[\s,]+)*"
    r"(?:remind\s+me\s+(?:to|at|on|in|tomorrow|tonight|about|later|every|this|next)\b"
    r"|set\s+(?:a|an|me\s+a)\s+(?:reminder|alarm|timer)\b"
    r"|add\b[^.?!\n]{0,80}\bto\s+(?:my\s+)?(?:(?:to-?do|todo|shopping|grocery)\s*)?list\b"
    r"|(?:don'?t|do\s+not)\s+let\s+me\s+forget\b)",
    re.IGNORECASE,
)

# "What if it's dropped from 80 m?": a hypothetical that continues a thread.
_HYPOTHETICAL_RE = re.compile(
    r"\s*(?:(?:and|but|so|ok|okay)\s+)?(?:what\s+(?:if|about)|how\s+about|suppose|imagine)\b",
    re.IGNORECASE,
)

# A supplied nuclear mass is a chemistry mass-defect calculation. A bare
# ``mass =`` is not that mass, so those words stay on the unverified physics path.
_SUPPLIED_NUCLEAR_MASS_RE = re.compile(
    r"\b(?:mass defect|binding energy)\b[\s\S]{0,80}\bnuclear mass\s*=\s*-?(?:\d|\.\d)",
    re.IGNORECASE,
)


# Detection reads the head and tail of a long message, where the question sits
# in a paste. It runs on every chat turn, so its cost must not grow with the
# paste; the extractors still read the whole request, up to their own cap.
_DETECTION_WINDOW = 4_000

# Detection and extraction are pure functions of the text, and one chat turn
# asks both questions of the same line from turn prep, routing, the prompt
# builder, and the direct reply. Each turn pays once.
_CACHE_SIZE = 128


def _named_symbol_request(text: str) -> str | None:
    """``F = 20 N, m = 5 kg, find a`` as the named question the binder reads."""
    from app.modules.physics.symbol_givens import named_symbol_request

    return named_symbol_request(text, lambda request: _extract_physics_intent(request) is not None)


@reading(declined=False)
@lru_cache(maxsize=_CACHE_SIZE)
def needs_physics(text: str) -> bool:
    """True for a verified template or an unmistakable physics-only request."""
    from app.modules.physics.symbolic.request import is_symbolic_physics_request

    if is_symbolic_physics_request(text):
        return True
    if _ERRAND_RE.search(text) is not None:
        return False
    from app.modules.physics.force_pictures import force_picture

    # "Draw the forces on a hanging mass" has no number and is physics all the same.
    if force_picture(text) is not None:
        return True
    if _named_symbol_request(text) is not None:
        return True
    normalized = normalize_symbolic_request(fold_scientific(text), limit=_MAX_SUBJECT_TEXT)
    if not normalized:
        return False
    from app.modules.physics.numbers import normalize_physics_units

    # The spellings the extractors read: "m per s squared", "accelaration".
    cleaned = normalize_physics_units(cap_text_head_tail(normalized, _DETECTION_WINDOW))
    if _SUPPLIED_NUCLEAR_MASS_RE.search(cleaned) is not None:
        return False
    if _ADVANCED_PHYSICS_RE.search(cleaned) is not None:
        return True
    from app.modules.physics.extractors.drag import closed_drag_request

    if closed_drag_request(cleaned):
        return True
    if not any(char.isdigit() for char in cleaned):
        return _DIGIT_FREE_PHYSICS_RE.search(cleaned) is not None
    if has_supported_physics_cue(cleaned):
        return True
    # The catalog is a cue too: a question that states one law's inputs and
    # asks for its result exactly ("the weight of a 70 kg person") is physics.
    from app.modules.physics.binding import bind_physics_intent

    if bind_physics_intent(cleaned) is not None:
        return True
    # So is a complete reading of a trip in two stages, a chase, or two legs at
    # right angles, which no single law fits.
    from app.modules.physics.extractors.relative_motion import (
        extract_chase_intent,
        extract_legs_intent,
    )
    from app.modules.physics.extractors.two_stage import extract_two_stage_intent

    if any(
        reader(cleaned) is not None
        for reader in (extract_two_stage_intent, extract_chase_intent, extract_legs_intent)
    ):
        return True
    # A question in lettered parts whose parts a law reads, though the whole is read by none.
    from app.modules.physics.split_parts import reads_in_parts

    return reads_in_parts(cleaned)


def extract_physics_intent(text: str) -> PhysicsIntent | None:
    """Extract one complete physics request without entering math dispatch.

    Callers get their own copy, so none can change what the next one reads.
    """
    intent = _extract_physics_intent(text)
    return None if intent is None else intent.model_copy(deep=True)


def _answers_another_kind(intent: PhysicsIntent) -> bool:
    """An extractor's law whose catalog result is not what the question asks.

    "A 2 kW kettle heats 1.5 kg of water from 20 °C to 100 °C. How long?"
    names Q = mcΔT's values, and the heat it gives is not a time; the block
    would refuse it, and the law that answers (t = mcΔT/P) was never tried.
    Only a law whose binding states its result is checked here.
    """
    from app.modules.physics.catalog import formula_spec
    from app.services.law_binding.units import dimension_of

    spec = formula_spec(intent.physics_op or "")
    # A law that solves for any of its quantities, or a list of asked parts,
    # is checked by the block, which knows each result.
    if (
        spec is None
        or spec.binding is None
        or spec.solve_for
        or len(intent.asked) != 1
        or intent.requested_ops
    ):
        return False
    produced = {dimension_of(unit) for unit in spec.binding.result}
    return not set(intent.asked) <= produced


@reading(declined=None)
@lru_cache(maxsize=_CACHE_SIZE)
def _extract_physics_intent(text: str) -> PhysicsIntent | None:
    from app.modules.physics.request import complete_physics_intent, prepare_physics_request

    named = _named_symbol_request(text)
    if named is not None:
        return _extract_physics_intent(named)

    cleaned = normalize_symbolic_request(fold_scientific(text), limit=_MAX_PHYSICS_REQUEST)
    if not cleaned:
        return None
    from app.modules.physics.ask import asked_phrases, has_ask
    from app.modules.physics.bodies import main_question
    from app.modules.physics.claims import question_without_claims

    # A side question about another body is not the main question's setting
    # ("Would it be different on Mars?"), and a student's own result is never a
    # given ("I got 19.8 m/s"). Both are read out before anything binds a value.
    cleaned = question_without_claims(main_question(cleaned))
    request = prepare_physics_request(cleaned)
    if request.rejected:
        return None
    if request.collision is not None:
        return complete_physics_intent(request.collision, request)
    if not has_ask(request.text):
        # "A ball is dropped from 80 m." asks nothing. An extractor's default
        # (the fall time) would pick a question for the student.
        return None
    if _HYPOTHETICAL_RE.match(request.text) and not asked_phrases(request.text):
        # "What if it's dropped from 80 m?" asks the thread's question again;
        # alone it names none, and the fall time would be a guess at it.
        return None
    from app.modules.physics.extractors.two_stage import (
        extract_two_stage_intent,
        whole_trip_of_two_stages,
    )

    if whole_trip_of_two_stages(request.text):
        # A trip in two stages asked about whole: only the two-stage reading
        # answers it. One interval's law answered the first stage alone.
        two_stage = extract_two_stage_intent(request.text)
        return None if two_stage is None else complete_physics_intent(two_stage, request)
    for extractor in PHYSICS_EXTRACTORS:
        intent = extractor(request.text)
        if intent is not None:
            completed = complete_physics_intent(intent, request)
            if completed is not None and not _answers_another_kind(completed):
                return completed
            # The claim was refused: a given it left unused, or a different
            # asked quantity. Its law is not the question's, but a catalog law
            # may still fit exactly. Returning here left "orbits Earth at a
            # radius of 7 x 10^6 m" unanswered behind the altitude formula.
            break
    # Last: a question the extractors declined, or whose claim was refused,
    # may still state a catalog law's inputs plainly and ask for its result.
    # Only one exact fit is answered, and only for text the physics gate calls
    # physics, so the binder adds answers to physics questions and never takes
    # a question from math.
    if not needs_physics(text):
        return None
    from app.modules.physics.binding import bind_physics_intent

    bound = bind_physics_intent(request.text)
    return None if bound is None else complete_physics_intent(bound, request)
