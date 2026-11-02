"""One normalized description of how a learner wants a math reply presented.

The solver answers *what is true*.  This module answers the separate question
of *how much of that truth the current turn may reveal*.  Keeping that decision
in one bounded, deterministic classifier prevents prompt generation, direct
rendering, follow-ups, and fence attachment from interpreting the same wording
differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_MAX_REQUEST = 1000
_WORD = re.compile(r"[a-z0-9']+")


class MathResponseMode(StrEnum):
    SOLVE = "solve"
    ANSWER_ONLY = "answer_only"
    STEPS = "steps"
    EXPLAIN = "explain"
    DETAILED = "detailed_explanation"
    HINT = "hint"
    EXAMPLES = "examples"
    CHECK = "check_my_answer"
    PROOF = "proof"
    GRAPH = "graph"


class MathMethod(StrEnum):
    FACTORING = "factoring"
    QUADRATIC_FORMULA = "quadratic_formula"
    SUBSTITUTION = "substitution"
    ELIMINATION = "elimination"


@dataclass(frozen=True)
class MathResponseIntent:
    mode: MathResponseMode = MathResponseMode.SOLVE
    requested_method: MathMethod | None = None
    reveal_answer: bool = True
    referential: bool = False

    @property
    def wants_explanation(self) -> bool:
        return (
            self.mode
            in {
                MathResponseMode.STEPS,
                MathResponseMode.EXPLAIN,
                MathResponseMode.DETAILED,
                MathResponseMode.EXAMPLES,
                MathResponseMode.PROOF,
            }
            or self.requested_method is not None
        )

    @property
    def wants_detailed_explanation(self) -> bool:
        return self.mode in {
            MathResponseMode.EXPLAIN,
            MathResponseMode.DETAILED,
            MathResponseMode.PROOF,
        }


_NEGATIONS = frozenset({"no", "not", "without", "don't", "dont", "never"})
_EXPLANATION_NOUNS = frozenset(
    {"explanation", "explanations", "steps", "step", "work", "working", "reasoning"}
)
_ANSWER_NOUNS = frozenset(
    {"answer", "answers", "solution", "solutions", "root", "roots", "number", "value"}
)
_HINT_WORDS = frozenset({"hint", "nudge", "clue"})
_CHECK_WORDS = frozenset({"check", "correct", "right", "mistake", "wrong", "grade", "mark"})
_DETAIL_WORDS = frozenset({"detailed", "thorough", "fully", "complete", "comprehensive"})
_SCHOOL_METHOD_WORDS = frozenset(
    {
        "addition",
        "borrowing",
        "carrying",
        "division",
        "multiplication",
        "regrouping",
        "subtraction",
    }
)
_REFERENTIAL_VOCAB = frozenset(
    {
        "a",
        "again",
        "another",
        "answer",
        "an",
        "by",
        "can",
        "clue",
        "could",
        "did",
        "different",
        "do",
        "explain",
        "example",
        "examples",
        "get",
        "give",
        "giving",
        "got",
        "help",
        "hint",
        "how",
        "it",
        "me",
        "method",
        "one",
        "only",
        "please",
        "proof",
        "prove",
        "reason",
        "result",
        "away",
        "show",
        "so",
        "steps",
        "step",
        "that",
        "the",
        "this",
        "through",
        "walk",
        "way",
        "why",
        "with",
        "without",
        "work",
        "what",
        "would",
        "you",
        "your",
    }
)


def _tokens(text: str) -> list[str]:
    if not text or len(text) > _MAX_REQUEST:
        return []
    return _WORD.findall(text.lower().translate({0x2019: "'"}))


def _near(tokens: list[str], left: frozenset[str], right: frozenset[str], span: int = 3) -> bool:
    """Whether semantic word groups occur close enough to modify one another."""
    for index, token in enumerate(tokens):
        if token not in left:
            continue
        if any(candidate in right for candidate in tokens[index + 1 : index + span + 1]):
            return True
    return False


def _requested_method(tokens: list[str]) -> MathMethod | None:
    def requested_at(index: int) -> bool:
        if any(word in _NEGATIONS for word in tokens[max(0, index - 4) : index]):
            return False
        # A bare imperative such as “Factor x^2-5x+6” describes the operation,
        # not a requested presentation method.  Method intent needs a nearby
        # grammatical cue such as “using”, “by”, or “with”.
        if tokens[index] in {"factor", "factoring", "factorisation"}:
            return any(
                word in {"by", "method", "use", "using", "with"}
                for word in tokens[max(0, index - 3) : index + 3]
            )
        return True

    for index, word in enumerate(tokens):
        if word == "quadratic" and tokens[index : index + 2] == ["quadratic", "formula"]:
            if requested_at(index):
                return MathMethod.QUADRATIC_FORMULA
        if word in {"factor", "factoring", "factorisation"} and requested_at(index):
            return MathMethod.FACTORING
        if word in {"substitution", "substitute"} and requested_at(index):
            return MathMethod.SUBSTITUTION
        if word in {"elimination", "eliminate"} and requested_at(index):
            return MathMethod.ELIMINATION
    return None


def _withhold_answer(tokens: list[str]) -> bool:
    joined = " ".join(tokens)
    if any(word in tokens for word in _HINT_WORDS):
        return True
    if "give it away" in joined or "giving it away" in joined:
        return True
    # "do not tell me either root", "without giving the solution", etc.
    for index, token in enumerate(tokens):
        if token not in _NEGATIONS:
            continue
        tail = tokens[index + 1 : index + 7]
        if any(noun in tail for noun in _ANSWER_NOUNS) and any(
            verb in tail
            for verb in ("give", "giving", "tell", "telling", "reveal", "show", "solve")
        ):
            return True
    return False


def _answer_only(tokens: list[str]) -> bool:
    joined = " ".join(tokens)
    if _near(tokens, frozenset({"only", "just"}), _ANSWER_NOUNS):
        return True
    if _near(tokens, _ANSWER_NOUNS, frozenset({"only"})):
        return True
    if any(phrase in joined for phrase in ("just give me x", "just give me the result")):
        return True
    return _near(tokens, _NEGATIONS, _EXPLANATION_NOUNS, span=4) or any(
        phrase in joined for phrase in ("don't explain", "dont explain", "do not explain")
    )


def _is_referential(tokens: list[str], mode: MathResponseMode) -> bool:
    if mode not in {
        MathResponseMode.STEPS,
        MathResponseMode.EXPLAIN,
        MathResponseMode.DETAILED,
        MathResponseMode.HINT,
        MathResponseMode.EXAMPLES,
        MathResponseMode.PROOF,
    }:
        return False
    # A follow-up may be natural prose, but every content word must be about
    # the preceding answer.  "How do plants grow?" therefore cannot capture
    # an old equation merely because it begins with "how".
    return bool(tokens) and len(tokens) <= 14 and set(tokens) <= _REFERENTIAL_VOCAB


def classify_math_response_intent(text: str) -> MathResponseIntent:
    tokens = _tokens(text)
    if not tokens:
        return MathResponseIntent()
    joined = " ".join(tokens)
    how_index = tokens.index("how") if "how" in tokens else -1
    quantitative_how = bool(
        how_index >= 0
        and how_index + 1 < len(tokens)
        and tokens[how_index + 1] in {"far", "high", "hot", "long", "many", "much", "old"}
    )
    # A definition such as "What is division with remainder?" describes the
    # concept; ``with`` is not a request to execute the written method.  A
    # concrete calculation still contains at least one numeric token and can
    # opt into its requested school procedure below.
    conceptual_definition = tokens[:2] == ["what", "is"] and not any(
        token.isdigit() for token in tokens
    )
    method = _requested_method(tokens)
    reveal = not _withhold_answer(tokens)
    has_check = any(word in tokens for word in _CHECK_WORDS) and (
        "my" in tokens or "i" in tokens or "am" in tokens
    )
    if not reveal:
        mode = MathResponseMode.HINT
    elif has_check:
        mode = MathResponseMode.CHECK
    elif _answer_only(tokens):
        mode = MathResponseMode.ANSWER_ONLY
    elif "prove" in tokens or "proof" in tokens:
        mode = MathResponseMode.PROOF
    elif "example" in tokens or "examples" in tokens:
        mode = MathResponseMode.EXAMPLES
    elif any(word in tokens for word in _DETAIL_WORDS) or (
        ("every" in tokens or "each" in tokens or "all" in tokens) and "step" in joined
    ):
        mode = MathResponseMode.DETAILED
    elif (
        "walk" in tokens
        or "step" in tokens
        or "steps" in tokens
        or "working" in tokens
        or ("show" in tokens and "work" in tokens)
        or (
            not conceptual_definition
            and any(word in tokens for word in _SCHOOL_METHOD_WORDS)
            and any(cue in tokens for cue in ("by", "show", "use", "using", "with"))
        )
        or ("show" in tokens and set(tokens) <= _REFERENTIAL_VOCAB)
        or ("do" in tokens and "again" in tokens and set(tokens) <= _REFERENTIAL_VOCAB)
    ):
        mode = MathResponseMode.STEPS
    elif (
        "teach" in tokens
        or "explain" in tokens
        or "why" in tokens
        or conceptual_definition
        or ("how" in tokens and not quantitative_how)
        or set(tokens) == {"what"}
        or (
            ("example" in tokens or "examples" in tokens) and ("give" in tokens or "show" in tokens)
        )
        or ("another" in tokens and ("way" in tokens or "method" in tokens))
    ):
        mode = MathResponseMode.EXPLAIN
    elif "graph" in tokens or "plot" in tokens or "sketch" in tokens:
        mode = MathResponseMode.GRAPH
    elif method is not None:
        mode = MathResponseMode.STEPS
    else:
        mode = MathResponseMode.SOLVE
    return MathResponseIntent(
        mode=mode,
        requested_method=method,
        reveal_answer=reveal,
        referential=_is_referential(tokens, mode),
    )


def response_intent_prompt(intent: MathResponseIntent) -> str:
    """Small model-facing contract derived from the same policy enforcement uses."""
    if not intent.reveal_answer:
        return (
            "Response intent: HINT ONLY. Do not state, imply, fence, label, or expose the final "
            "answer or roots. Give the smallest useful next move and let the learner try."
        )
    if intent.mode == MathResponseMode.ANSWER_ONLY:
        return (
            "Response intent: ANSWER ONLY. Return the verified result and required conditions only."
        )
    if intent.mode == MathResponseMode.PROOF:
        return "Response intent: PROOF. Prove the claim without changing the verified result."
    if intent.mode == MathResponseMode.EXAMPLES:
        return "Response intent: EXAMPLES. Teach with a relevant example before generalizing."
    if intent.requested_method is not None:
        return f"Response intent: use the requested method ({intent.requested_method.value})."
    if intent.mode in {MathResponseMode.STEPS, MathResponseMode.DETAILED}:
        return "Response intent: show the verified working, one transformation per step."
    if intent.mode == MathResponseMode.EXPLAIN:
        return "Response intent: explain why the verified steps are valid."
    return "Response intent: solve the complete request."


# Response wrappers are removed before extraction.  This list lives here—not
# in every downstream consumer—and contains grammatical constructions rather
# than individual test sentences.
_PRESENTATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?explain\s+"
        r"(?:why\s+)?(?:each|every|the)\s+steps?\s+(?:is|are)\s+valid\s+(?:for|in)\s+",
        r"\b(?:and\s+)?explain\s+(?:why\s+)?(?:each|every|the)\s+steps?\s+"
        r"(?:is|are)\s+valid\b",
        r"\b(?:and\s+)?explain\s+(?:each|every|the)\s+steps?\b(?:\s+to)?",
        r"\b(?:and\s+)?explain\s+(?:it\s+)?(?:step[ -]?by[ -]?step|the\s+steps?)\b",
        r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:explain|show\s+me)\s+how\s+to\s+",
        r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?explain\s+",
        r"\b(?:do\s+not|don't|dont|without)\s+(?:give|giving|tell|telling|reveal|revealing|show|showing)(?:\s+me)?\s+(?:the|either|any)?\s*(?:answer|solution|roots?)\b",
        r"\b(?:help)(?:\s+me)?\s+without\s+giving\s+it\s+away\b",
        r"\b(?:please\s+)?(?:show|give)(?:\s+me)?\s+(?:all|every|each|the|your)?\s*(?:steps?|work|working)\b",
        r"\b(?:walk)(?:\s+me)?\s+through(?:\s+it)?\b",
        r"\b(?:step[ -]?by[ -]?step)\b",
        r"\b(?:(?:final|just|only)\s+(?:the\s+)?(?:answer|result)|(?:answer|result)\s+only)\b",
        r"\b(?:just\s+give\s+me\s+[a-z])\b",
        r"\b(?:no|without)\s+(?:steps?|work|working|explanation|reasoning)\b",
        r"\b(?:no|without)\s+(?:(?:a|the)\s+)?(?:graph|plot|sketch)\b",
        r"\b(?:do\s+not|don't|dont)\s+(?:graph|plot|sketch)\b",
        r"\b(?:do\s+not|don't|dont)\s+explain\b",
        r"\b(?:teach)(?:\s+me)?(?:\s+how\s+to)?\s+(?:solve)?\b",
        r"\b(?:give|show)(?:\s+me)?\s+(?:one|a|the)?\s*(?:hint|nudge|clue)(?:\s+for)?\b",
        r"\b(?:do\s+not|don't|dont)\s+(?:use\s+)?(?:the\s+)?(?:quadratic\s+formula|factor(?:ing)?|factorisation|substitution|elimination)(?:\s+(?:it|this))?\b",
        r"\b(?:using|use|with|by)\s+(?:the\s+)?(?:quadratic\s+formula|factoring|factorisation|substitution|elimination)\b",
        # "Use the distance formula to find ...": the method a coordinate answer is worked by.
        r"\b(?:using|use|with|by|apply|applying)\s+(?:the\s+)?(?:distance|slope|gradient|midpoint)\s+formula(?:\s+to)?\b",
        r"\b(?:keep)\s+(?:the\s+)?(?:variable|x)\s+lowercase(?:\s+in\s+the\s+final\s+answer)?\b",
        # Asking for the answer to be checked is presentation: the solve still runs.
        r"\b(?:and\s+)?(?:double[- ]check|check|verify|confirm|prove)\s+(?:it|that|this|"
        r"(?:your|the)\s+(?:answer|solution|result))\b",
        r"\b(?:and\s+)?show\s+(?:me\s+)?(?:that\s+)?it\s+works\b",
        r"\b(?:no|without|skip(?:ping)?|don'?t|do\s+not)\s+(?:the\s+|a\s+|any\s+)?"
        r"(?:check|checking|checks|verify|verifying|verification|proof)\b",
        r"^\s*(?:please\s+)?(?:check|verify)\s+(?=\S)",
        r"\b(?:and\s+)?(?:double[- ]check|check|verify)[ .!?]*$",
    )
)


# The frame around a question that never changes what it asks: a polite or casual opener
# ("Can you", "Hey,", "I need", "Help me"), an actor's name before what they do ("Kebede
# throws two dice", "John draws a card"), and how the answer should be written ("in
# simplest form", "Express your answer as a fraction", "Round to the nearest tenth",
# "in units"). Units and rounding are frame only for answers that have neither a unit nor
# a precision to choose (a probability, a coordinate line), so readers opt in by calling
# ``strip_ask_frame``; the presentation patterns above apply to every reader. An answer
# asked in terms of π is never frame: the card would be worked with π itself.
_OPENER = (
    r"(?:hey|hi|hello|ok|okay|so|please|(?:can|could|would|will)\s+(?:you|u)|can\s+i\s+(?:get|have)"
    r"|i\s+(?:need|want)(?:\s+to\s+(?:know|find|get))?|help\s+me(?:\s+to)?|tell\s+me|quick\s+question)"
)
_ASK_FRAME_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"(?:^|(?<=[.?!]\s)){_OPENER}\b[,:!]?(?:\s+{_OPENER}\b[,:!]?)*\s*",
        # The format words only: "as a fraction, assuming the first die is even" keeps its
        # condition, so the reader sees it and declines rather than answer without it.
        r"\b(?:express|give|write|leave|state|present)\s+(?:your|the)\s+answers?\s+"
        r"(?:as|in)\b(?![^.?!]*(?:\u03c0|\\pi|\bpi\b))[^.?!,;:]*?(?=\s*(?:[.?!,;:]|$"
        r"|\b(?:assuming|given|if|when|where|which|that|unless|provided|but|and|because|since"
        r"|with|for|then)\b))",
        r"\b(?:in|to)\s+(?:its\s+|the\s+)?(?:simplest|lowest)\s+(?:form|terms)\b",
        r"\b(?:round(?:ed)?|correct)\s+(?:your\s+answer\s+|it\s+)?to\s+(?:the\s+nearest\s+"
        r"(?:tenth|hundredth|thousandth|whole(?:\s+number)?|integer|unit)|\d+\s+(?:decimal\s+places?"
        r"|significant\s+figures?))\b",
        r"\bin\s+(?:units|cm|centimet(?:er|re)s|mm|millimet(?:er|re)s|met(?:er|re)s|km|inches"
        r"|feet|ft)\b",
    )
)
# A name before what its owner does: "Abebe rolls", "John draws". Not a number word or a
# question word: "Two rolls of a die", "What draws ..." keep theirs.
_ACTOR = re.compile(
    r"\b(?!(?:One|Two|Three|Four|Five|Six|The|A|An|What|Which|Each|Every|This|That|It|He|She"
    r"|They|You|We|If|When|Then|Find)\b)[A-Z][a-z]+\s+(?=(?:rolls|throws|tosses|draws|picks"
    r"|selects|chooses|takes|flips|spins|rolled|threw|tossed|drew|picked|selected|chose|took"
    r"|flipped|spun)\b)"
)


def strip_ask_frame(text: str) -> str:
    """The question without its frame: openers, actors, answer format and presentation."""
    result = _ACTOR.sub("", text)
    for pattern in _ASK_FRAME_PATTERNS:
        result = pattern.sub(" ", result)
    return strip_math_response_wrappers(result)


def strip_math_response_wrappers(text: str) -> str:
    """Remove presentation metadata without changing the mathematical task."""
    result = text
    for pattern in _PRESENTATION_PATTERNS:
        result = pattern.sub(" ", result)
    result = " ".join(result.split())
    result = re.sub(r"^\s*(?:and|then)\b", "", result, flags=re.IGNORECASE)
    # Wrapper removal can leave punctuation around a now-orphaned conjunction
    # ("answer; no graph and no steps" -> "; and ."). Remove that tail as
    # presentation debris, not as part of the mathematical expression.
    result = re.sub(
        r"\b(?:and|then)[ :;,.?]*$",
        "",
        result,
        flags=re.IGNORECASE,
    )
    # Do not strip ``-`` or ``!``: they may be unary minus and factorial.
    # Direct-reply completeness checks decide whether a trailing exclamation
    # mark was punctuation; extraction must never silently change the math.
    return result.strip(" :;,.?")
