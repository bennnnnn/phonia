"""Whole-request integrity checks shared by every math extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.math.schemas import MathIntent

_ADDITIONAL_OPERATION = re.compile(
    r"\b(?:and|then|also|plus)\s+(?:then\s+)?"
    r"(?:solve|simplify|evaluate|calculate|compute|differentiate|integrate|"
    r"factor|expand|graph|plot|find|determine|convert|compare)\b",
    re.IGNORECASE,
)
_TRIG_CALL = re.compile(r"\b(?:sin|cos|tan|sec|csc|cot)\s*\(", re.IGNORECASE)
# ``log``, ``ln``, ``lg`` as written, with or without a bracket ("log base 2 of x").
_LOG_TERM = re.compile(r"\b(?:log|ln|lg)(?![a-z])", re.IGNORECASE)
_MEAN_AND_SPREAD = re.compile(
    r"\b(?:find|calculate|compute|determine|give|what\s+(?:is|are))\b"
    r"[^.?!]{0,30}\b(?:mean\b[^.?!]{0,30}\b(?:and|plus)\b[^.?!]{0,20}"
    r"(?:standard\s+deviation|stdev|variance)|"
    r"(?:standard\s+deviation|stdev|variance)\b[^.?!]{0,30}\b(?:and|plus)\b"
    r"[^.?!]{0,20}mean)\b",
    re.IGNORECASE,
)
_AREA_AND_PERIMETER = re.compile(
    r"\b(?:area\b[^.?!]{0,30}\band\b[^.?!]{0,20}\bperimeter|"
    r"perimeter\b[^.?!]{0,30}\band\b[^.?!]{0,20}\barea)\b",
    re.IGNORECASE,
)
_STATISTIC_NAME = (
    r"(?:z[-\s]?score|arithmetic\s+mean|mean|median|mode|range|variance|"
    r"standard\s+deviation|stdev)"
)
_MULTIPLE_REQUESTED_STATISTICS = re.compile(
    r"\b(?:find|calculate|compute|determine|give|what\s+(?:is|are))\b"
    rf"[^.?!]{{0,50}}\b{_STATISTIC_NAME}\b[^.?!]{{0,30}}\b(?:and|plus)\b"
    rf"[^.?!]{{0,30}}\b{_STATISTIC_NAME}\b",
    re.IGNORECASE,
)
_LABELED_Z_SCORE_OPERAND = re.compile(
    r"\b(?:mean(?:\s+score)?|standard\s+deviation|std(?:\s+dev)?|stdev)"
    r"(?:\s+is|\s*=)?\s+[+-]?(?:\d+(?:\.\d+)?|\.\d+)\b",
    re.IGNORECASE,
)
_GRAPH_REQUEST = re.compile(r"\b(?:graph|plot|sketch)\b", re.IGNORECASE)
_ROOT_OUTPUT_REQUEST = re.compile(
    r"\b(?:roots|zeros)\b"
    r"|\b(?:find|tell\s+me|give|determine|calculate|compute|what\s+is)\b"
    r"[^.?!]{0,40}\b(?:the|a|its)?\s*(?:root|zero)\b",
    re.IGNORECASE,
)
_NAMED_RADICAL = re.compile(
    r"\b(?:square|cube|fourth|fifth|sixth|seventh|eighth|n(?:th)?|"
    r"[2-9](?:nd|rd|th))\s+root\b",
    re.IGNORECASE,
)
_NUMBER_SET_DOMAIN = (
    r"(?:(?:integers?|natural\s+numbers?|rationals?(?:\s+numbers?)?|"
    r"complex(?:\s+numbers?)?)\b|[\u2124\u2115\u211A\u2102]|"
    r"\\mathbb\s*\{\s*[ZNQC]\s*\})"
)
_REAL_NUMBER_SET = r"(?:\u211D|\\mathbb\s*\{\s*R\s*\})"
_REAL_PROSE_DOMAIN_END = r"\s+(?:(?:an?|any)\s+)?real(?:\s+numbers?)?\s*(?:$|[,.!?;)])"
_DOMAIN_ADJECTIVE = (
    r"(?:positive|negative|non[-\s]?negative|non[-\s]?positive|non[-\s]?zero|"
    r"odd|even|prime|composite)"
)
# Restriction verbs are composed (optional modal, adverbs, linking verb) so
# rephrasings such as "has to be" or "can only be" also fail closed. A negated
# phrase never takes the real-domain exemption: "x cannot be real" restricts.
_LINK_AUXILIARY = (
    r"(?:must|should|shall|will|would|can|could|may|might|"
    r"ha(?:s|ve)(?:\s+got)?\s+to|needs?\s+to|ought\s+to|do(?:es)?)"
)
_LINK_ADVERB = r"(?:only|always|ever|strictly|also|still|necessarily)"
_LINK_VERB = (
    r"(?:is|are|was|were|be|being|to\s+be|equals?|remains?|stays?|"
    r"belongs?\s+to|lies?\s+(?:in|between|within))"
)
_AFFIRMATIVE_LINK = rf"(?:{_LINK_AUXILIARY}\s+)?(?:{_LINK_ADVERB}\s+){{0,2}}{_LINK_VERB}"
_NEGATED_LINK = (
    rf"(?:(?:(?:{_LINK_AUXILIARY}\s+)?(?:{_LINK_ADVERB}\s+)?(?:not|never)|cannot|"
    rf"[a-z]+n['\u2019]t)\s+(?:{_LINK_ADVERB}\s+)?{_LINK_VERB}|(?:is|are|was|were)n['\u2019]t)"
)
_LINKING_PHRASE = rf"(?:{_NEGATED_LINK}|{_AFFIRMATIVE_LINK})"
_DOMAIN_CUE = (
    r"(?:(?:for|where|also|with|and|if)\b|"
    r"(?:assum(?:e|ing)|suppos(?:e|ing)|given|provided)(?:\s+that)?\b|"
    r"(?:let|take|consider)\b|such\s+that\b|subject\s+to\b|"
    r"(?:under|on)\s+(?:the\s+)?condition\s+that\b|[,;])"
)
_EQUALITY_DOMAIN_CUE = (
    r"(?:where\b|(?:assum(?:e|ing)|suppos(?:e|ing)|given|provided)"
    r"(?:\s+that)?\b|(?:let|take|consider)\b|such\s+that\b|subject\s+to\b|"
    r"(?:under|on)\s+(?:the\s+)?condition\s+that\b)"
)
_NONDEFAULT_DOMAIN = re.compile(
    rf"\b(?:in|over)\s+(?:the\s+)?{_NUMBER_SET_DOMAIN}"
    rf"|[a-z]\s*(?:∈|\\in\b)\s*(?!{_REAL_NUMBER_SET}(?:$|[\s,;.:)\]]))"
    rf"|{_DOMAIN_CUE}\s+[a-z]\s+in\s*[\[(]"
    rf"|{_DOMAIN_CUE}\s+[a-z]\s*(?:!=|≠|[<>≤≥])"
    rf"|{_DOMAIN_CUE}\s+[a-z]\s+{_NEGATED_LINK}\b"
    rf"|{_DOMAIN_CUE}\s+[a-z]\s+{_AFFIRMATIVE_LINK}\b(?!{_REAL_PROSE_DOMAIN_END})"
    rf"|{_DOMAIN_CUE}\s+[a-z]\s+"
    rf"(?:{_DOMAIN_ADJECTIVE}|(?:an?\s+)?{_NUMBER_SET_DOMAIN})"
    rf"|{_DOMAIN_CUE}\s+(?:an?\s+)?(?:{_DOMAIN_ADJECTIVE}|{_NUMBER_SET_DOMAIN})"
    r"\s+[a-z]\b",
    re.IGNORECASE,
)
_LINKED_EQUALITY_DOMAIN = re.compile(
    rf"{_EQUALITY_DOMAIN_CUE}\s+(?P<variable>[a-z])\s*={{1,2}}(?!=)",
    re.IGNORECASE,
)
_SIGNED_OUTPUT_RESTRICTION = re.compile(
    rf"\b(?:(?:the|only)\s+){{0,2}}{_DOMAIN_ADJECTIVE}\s+"
    r"(?:real\s+)?(?:roots?|solutions?)\b(?:\s+only)?"
    rf"|\b(?:roots?|solutions?)\s+(?:that\s+)?(?:{_LINKING_PHRASE}\s+)?"
    rf"(?:(?:not|never|{_LINK_ADVERB})\s+)?{_DOMAIN_ADJECTIVE}\b",
    re.IGNORECASE,
)
# A feature of the equation was asked for, not its solutions. Solving
# "find the vertex of y = x^2 - 6x + 5" for x answered a different question
# with a verified card; the feature rules in ``school/equation_features``
# read these, and anything they decline stays with the model.
_EQUATION_FEATURE_REQUEST = re.compile(
    r"\b(?:vertex|vertices|turning\s+points?|(?:axis|line)\s+of\s+symmetry|intercepts?|"
    r"discriminant|(?:sum|product)\s+of\s+(?:the\s+|its\s+)?(?:roots|zeros|zeroes|solutions)|"
    r"slope|gradient|parallel|perpendicular|tangent|normal\s+to|asymptotes?|"
    r"maximum|minimum|range|domain|period|amplitude|ph|poh)\b",
    re.IGNORECASE,
)
# "... has exactly one solution": a condition on the equation, not the equation.
_SOLUTION_COUNT_CONDITION = re.compile(
    r"\b(?:has|have|having)\s+(?:exactly\s+|only\s+)?(?:one|two|no|1|2|a\s+single|a\s+repeated|"
    r"a\s+double|equal|repeated|distinct|real|infinitely\s+many)\b[^.?!]{0,30}"
    r"\b(?:solutions?|roots?|zeros?|zeroes?)\b",
    re.IGNORECASE,
)
# Inequalities keep "the range of values of x for which ..." as a solve.
_SOLVED_EQUATION_KINDS = frozenset({"equation", "system"})
# A point the asked object passes through, starts from or holds ("the image of (2, 3) in the
# line y = x", "the line through (1, 2) and the intersection of y = x and y = 2x - 1", "find
# k if (1, 5) lies on y = kx + 3") makes the ask about that point, not the equation's
# solutions. A point to check ("check that (3, 2) works", "is the solution (3, 1)?") or an
# interval ("on (0, 10)") leaves the solve whole.
_POINT_LITERAL = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)")
_POINT_OF_THE_ASK = re.compile(
    r"\b(?:through|thru|of|joining|connecting|containing)\s+(?:the\s+point\s+)?"
    r"(?:[A-Za-z][\'\u2019\u2032]?\s*)?\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)"
    r"|\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)\s+(?:lies|lie|is|are)\s+on\b",
    re.IGNORECASE,
)
_DOMAIN_BLIND_KINDS = frozenset(
    {"equation", "system", "inequality", "calculus", "limit", "graph", "graph_pair"}
)


@dataclass(frozen=True)
class ConsumptionAudit:
    complete: bool
    leftovers: tuple[str, ...] = ()


def _side_pattern(side: str) -> str:
    """Match one extracted equation side while allowing source whitespace."""
    compact = re.sub(r"\s+", "", side)
    return r"\s*".join(re.escape(char) for char in compact)


def _linked_equality_would_be_dropped(text: str, intent: MathIntent) -> bool:
    """Return true only when a linked equality is absent from a typed system."""
    matches = list(_LINKED_EQUALITY_DOMAIN.finditer(text))
    if not matches:
        return False
    represented_equations = intent.system_equations or []
    if intent.kind == "equation" and intent.lhs is not None and intent.rhs is not None:
        represented_equations = [(intent.lhs, intent.rhs)]
    if not represented_equations:
        return True
    for match in matches:
        source_equation = text[match.start("variable") :]
        represented = any(
            re.match(
                rf"^{_side_pattern(lhs)}\s*={{1,2}}\s*{_side_pattern(rhs)}"
                r"(?=$|[\s,;.?!])",
                source_equation,
                re.IGNORECASE,
            )
            is not None
            for lhs, rhs in represented_equations
        )
        if not represented:
            return True
    return False


def audit_math_request(text: str, intent: MathIntent) -> ConsumptionAudit:
    """Reject semantic components the chosen intent cannot represent.

    Extractors remain responsible for their closed grammar. This final seam
    catches cross-extractor partial matches: a valid first expression must not
    hide another requested operation, statistic, trig term, or measurement.
    """
    leftovers: list[str] = []
    statistics_text = (
        _LABELED_Z_SCORE_OPERAND.sub("", text) if intent.school_op == "z_score" else text
    )
    additional = _ADDITIONAL_OPERATION.search(text)
    if additional is not None and _prior_math_request(text[: additional.start()]):
        leftovers.append("additional requested operation")
    statistics_represented = _summary_statistics_represented(statistics_text, intent)
    if _MEAN_AND_SPREAD.search(statistics_text) and not statistics_represented:
        # One statistics intent carries one result unless ``stats_ops`` names
        # every requested summary; otherwise declining is the only atomic answer.
        leftovers.append("additional requested statistic")
    if _MULTIPLE_REQUESTED_STATISTICS.search(statistics_text) and not statistics_represented:
        # One MathIntent carries one statistical result. Different requested
        # summaries must be represented together or declined together. Input
        # labels such as "mean 72 and standard deviation 8" are deliberately
        # excluded: they are givens for a z-score, not requested outputs.
        leftovers.append("multiple requested statistics")
    if _AREA_AND_PERIMETER.search(text) and not (intent.wants_area and intent.wants_perimeter):
        # Supported geometry intents retain both requested flags and their
        # canonical diagram contains both values. Direct output stays off for
        # those multipart cases, but the model receives both verified facts.
        # Reject only when the chosen extractor silently lost one quantity.
        leftovers.append("additional requested measurement")
    source_trig_calls = len(_TRIG_CALL.findall(text))
    intent_text = " ".join(
        part for part in (intent.expr, intent.expr2, intent.lhs, intent.rhs) if part
    )
    if source_trig_calls > len(_TRIG_CALL.findall(intent_text)):
        leftovers.append("unconsumed trigonometric term")
    if len(_LOG_TERM.findall(text)) > len(_LOG_TERM.findall(intent_text)):
        # "log base 2 of (x+1) = 3" kept only (x+1) = 3 and verified x = 2.
        leftovers.append("unconsumed logarithm")
    root_request_text = _NAMED_RADICAL.sub("", text)
    if _GRAPH_REQUEST.search(text) and _ROOT_OUTPUT_REQUEST.search(root_request_text):
        # A graph intent has no typed roots result and a roots intent has no
        # graph result. Never certify whichever extractor happened to run first.
        leftovers.append("multiple requested function outputs")
    if intent.kind in _SOLVED_EQUATION_KINDS and (
        _EQUATION_FEATURE_REQUEST.search(text) or _SOLUTION_COUNT_CONDITION.search(text)
    ):
        leftovers.append("a feature of the equation, not its solutions")
    if intent.kind in _SOLVED_EQUATION_KINDS and _POINT_OF_THE_ASK.search(text):
        sides = " ".join(
            part for pair in intent.system_equations or [] for part in pair
        ) + " ".join(part for part in (intent.lhs, intent.rhs) if part)
        if not _POINT_LITERAL.search(sides):
            leftovers.append("a point beside the equation, not its solutions")
    has_unrepresented_domain = bool(_NONDEFAULT_DOMAIN.search(text))
    if _linked_equality_would_be_dropped(text, intent):
        has_unrepresented_domain = True
    if _SIGNED_OUTPUT_RESTRICTION.search(text):
        has_unrepresented_domain = True
    if intent.kind in _DOMAIN_BLIND_KINDS and has_unrepresented_domain:
        # These symbolic intents currently use their default real domain and
        # cannot encode an extra sign or number-set assumption. Never certify
        # a partial interpretation that silently discards that restriction.
        leftovers.append("unconsumed symbolic domain")
    return ConsumptionAudit(complete=not leftovers, leftovers=tuple(leftovers))


def _summary_statistics_represented(text: str, intent: MathIntent) -> bool:
    """True when the intent answers every summary statistic the text names."""
    if intent.kind != "statistics" or not intent.stats_ops or len(intent.stats_ops) < 2:
        return False
    from app.modules.math.match.discrete import requested_summary_stats

    return set(requested_summary_stats(text)) <= set(intent.stats_ops)


def _prior_math_request(prefix: str) -> bool:
    """Distinguish a second operation from prose such as "graph theory"."""
    if re.search(r"[=+\-*/^<>≤≥]", prefix) or re.search(r"\d", prefix):
        return True
    return (
        re.search(
            r"\b(?:solve|simplify|evaluate|calculate|compute|differentiate|integrate|"
            r"factor|expand|plot|find|determine|convert|compare)\b",
            prefix,
            re.IGNORECASE,
        )
        is not None
    )


def request_consumption_complete(text: str, intent: MathIntent) -> bool:
    return audit_math_request(text, intent).complete
