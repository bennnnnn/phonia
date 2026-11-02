"""A verified result answers the question asked, all of it, or is not shown.

A subject reader answers one thing. A question in parts, with several reactions, or with
options to choose from asks more, and the one thing it answered was shown as the checked
answer: "Electrons = 31" for "how many electrons in its valence shell? a 5 b 4 c 3 d 2",
"6" for "belongs to group: a IIIA b IVA c VIA d VIIA", "2 Fe + O₂ → 2 FeO" for the option
that forms iron(II) oxide, "3:2" for a five-part question, and part (a) alone of four pH
calculations (2026-10-30, Ethiopian Grade 7-12 chemistry books). Such a result is dropped
whole (its prompt block, its card and its instant reply), and the model answers the
question; a result that answers every part, or is one of the options, stays.

The readers must also be able to read the question at all (``turn_reading.readable``): a
question in another language, or with a number its writer's locale reads otherwise ("1.200"
from a Spanish user is 1200), gets no verified result, its card and pictures included.
"""

from __future__ import annotations

import re

from app.modules.chat.prompt_builder import SubjectFetch
from app.modules.turn_reading.readable import unreadable
from app.services.question_parts import labelled_parts
from app.services.solving import VerifiedSolveBlock

# A reaction: "→", "->", "⟶", "=>" between two sides.
_ARROW = re.compile(r"→|⟶|->|=>|⇌")
# A label opening an option or a part: "a 5", "(b) 4", "c) 3", "D Fe + O → FeO". Bare
# letters count only at a line's start or after two spaces, as a book prints options.
_LABEL = re.compile(
    r"(?:(?:^|(?<=\n)|(?<=\s\s))\(?([a-eA-E])(?:[).:]\s*|\s+)"
    r"|(?<=[\s(])\(?([a-eA-E])\)\s*)(?=\S)"
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_MARKUP = re.compile(r"\\[a-zA-Z]+|[{}$*_`\\]")


def labelled_choices(question: str) -> list[str]:
    """The texts of a run of two or more labels in order (a, b, c …), or none."""
    labels = [
        (match.start(), match.end(), (match.group(1) or match.group(2)))
        for match in _LABEL.finditer(question)
    ]
    for first, (_, _, letter) in enumerate(labels):
        if letter.lower() != "a":
            continue
        chain = [labels[first]]
        for later in labels[first + 1 :]:
            if later[2] == chr(ord(chain[-1][2]) + 1):
                chain.append(later)
        if len(chain) >= 2:
            ends = [start for start, _, _ in chain[1:]] + [len(question)]
            return [
                question[end:stop].splitlines()[0].strip() if question[end:stop] else ""
                for (_, end, _), stop in zip(chain, ends, strict=True)
            ]
    return []


# A verdict on a set of solutions, which only an equation or system to solve asks for.
_SOLUTION_VERDICT = re.compile(
    r"no\s+solutions?|infinitely\s+many|all\s+real\s+numbers|free\s+variable", re.IGNORECASE
)
_ASKS_TO_SOLVE = re.compile(
    r"\bsolve|\bsolutions?\b|\bconsistent\b|\bsatisf|\bfor\s+which\s+values?|\broots?\b",
    re.IGNORECASE,
)
# A size that is never negative: "the length of the radius", "how many". Not a speed or an
# oxidation number: a card may give a velocity or a charge its sign.
_MAGNITUDE_ASK = re.compile(
    r"\b(?:length|radius|diameter|side|perimeter|area|volume|mass|age)\b"
    r"|\bhow\s+(?:long|far|many|tall|wide|high|old)\b",
    re.IGNORECASE,
)
_SIGNED = re.compile(r"\\pm|±|(?:^|[=(,\s])-\s*\d")


# A proof has no value to certify: "Prove by induction …" showed "n = 0, 1/2, 1".
_ASKS_A_PROOF = re.compile(
    r"\b(?:prove|show\s+that|verify\s+that|demonstrate\s+that|by\s+induction)\b", re.IGNORECASE
)
# A value at a point: "the gradient at x = 3" is a number, not f'(x).
_AT_A_POINT = re.compile(
    r"\b(?:at|when|where)\s+(?:the\s+point\s+)?(?:[a-z]\s*=\s*-?\d|\(\s*-?\d)", re.IGNORECASE
)
# A variable left in a value; e and i are constants.
_FREE_VARIABLE = re.compile(r"(?<![a-zA-Z\\])[a-df-hj-z](?![a-zA-Z])")
_ASKS_AN_EQUATION = re.compile(r"\bequation\s+of\b", re.IGNORECASE)
# Solutions of a kind: "the rational zeros", "integer solutions".
_QUALIFIED_SOLUTIONS = re.compile(
    r"\b(?:rational|integer|whole[- ]number|natural[- ]number|positive)\s+"
    r"(?:zeros?|roots?|solutions?|values?|numbers?)",
    re.IGNORECASE,
)
# Values asked: "Find all the rational zeros of f(x) = …" got a factorisation (2026-10-31).
# "the cube root of …" is an operation, not an equation's roots.
_ASKS_VALUES = re.compile(
    r"\bzeros?\b|(?<!square )(?<!cube )(?<!fourth )\broots?\b"
    r"|\bsolutions?\s+(?:of|to|set|for)\b|\bsolve\b",
    re.IGNORECASE,
)
# What a value is stated with: "x = 2", "x ≈ 0.739".
_RELATION = re.compile(r"=|\\approx|≈")
_IN_TERMS_OF = re.compile(r"\bin\s+terms\s+of\b|\bfactori[sz]", re.IGNORECASE)
_INEQUALITY = re.compile(r"<|>|\\[lg]eq?\b|\\in\b|≤|≥")
_NOT_RATIONAL = re.compile(r"\d\.\d{3,}|\\sqrt|(?<![a-zA-Z\\])i(?![a-zA-Z])")


def answers_the_question(question: str, answer: str) -> bool:
    """``answer`` answers what ``question`` asks, all of it, and says something new: a
    whole question, not a restatement of it, a verdict only on an equation to solve, a size
    never signed, no value for a proof, a value at a point with no variable left, an
    equation where one is asked, and solutions of the kind asked."""
    return (
        answers_whole_question(question, answer)
        and not _restates(question, answer)
        and not (_SOLUTION_VERDICT.search(answer) and not _ASKS_TO_SOLVE.search(question))
        and not (
            _MAGNITUDE_ASK.search(_asked(question)) and _SIGNED.search(answer.rsplit("=", 1)[-1])
        )
        and not _ASKS_A_PROOF.search(question)
        and not (
            _AT_A_POINT.search(question)
            and not _ASKS_AN_EQUATION.search(question)
            and _FREE_VARIABLE.search(_right_side(answer))
        )
        and not (
            _ASKS_AN_EQUATION.search(question) and "=" not in answer and not _ARROW.search(answer)
        )
        and not (_QUALIFIED_SOLUTIONS.search(question) and _NOT_RATIONAL.search(answer))
        and not _expression_for_values(question, answer)
    )


def _expression_for_values(question: str, answer: str) -> bool:
    """Values asked (zeros, roots, solutions) and an expression given: a bare one, or a
    value with the variable it solves for still in it. "y = 4 - 2x/3" for "solve for y" is
    a value."""
    if not _ASKS_VALUES.search(_asked(question)) or _IN_TERMS_OF.search(question):
        return False
    if _INEQUALITY.search(answer):
        return False
    stated = _RELATION.split(answer)
    if len(stated) == 1:
        return _FREE_VARIABLE.search(_right_side(answer)) is not None
    named = set(_FREE_VARIABLE.findall(_right_side(stated[-2].split(",")[-1])))
    return bool(named & set(_FREE_VARIABLE.findall(_right_side(stated[-1]))))


def _right_side(answer: str) -> str:
    """What the answer gives: after its last "=", without LaTeX commands or units."""
    value = answer.rsplit("=", 1)[-1]
    # Units and command names go, never a command's argument: \frac{y}{2} keeps its y.
    value = re.sub(r"\\(?:mathrm|text|operatorname)\s*\{[^{}]*\}", " ", value)
    return re.sub(r"\\[a-zA-Z]+|\{|\}", " ", value)


# The sentences that ask: "… Find its acceleration.", "What is the radius?"
_ASKED_SENTENCE = re.compile(
    r"[^.?!\n]*\?|(?:^|(?<=[.!\n]))\s*(?:find|calculate|determine|state|give|work\s+out"
    r"|how|what|which)\b[^.?!\n]*",
    re.IGNORECASE,
)


def _asked(question: str) -> str:
    """The sentences of ``question`` that ask, or the whole of it when none does."""
    asked = " ".join(match.group(0) for match in _ASKED_SENTENCE.finditer(question))
    return asked or question


def _restates(question: str, answer: str) -> bool:
    """Every expression in ``answer`` is one in ``question`` as written: "the cube root of
    27a^3 + 54a^2b + …" certified the expression itself. A number with its unit is never a
    restatement: it may confirm the asker's own ("I got 19.8 m/s. Am I right?")."""
    asked = _squashed(question)
    pieces = [_squashed(piece) for piece in _ANSWER_PIECES.split(answer)]
    expressions = [piece for piece in pieces if _EXPRESSION.search(piece)]
    return bool(expressions) and all(
        re.search(rf"(?<![0-9.]){re.escape(piece)}(?![0-9a-z/^])", asked) for piece in expressions
    )


# Terms joined by an operator, a letter on one side: "27a3+54a2b", "x2-4".
_EXPRESSION = re.compile(r"[0-9a-z]\s*[+\-*]\s*[0-9a-z]")


# Between the pieces of an answer: a comma (not LaTeX's thin space "\,", nor one grouping a
# number's thousands, "E = 1,000,000 J"), ";", "\quad", a line.
_ANSWER_PIECES = re.compile(r"(?<![\\\d]),|(?<=\d),(?!\d{3}(?!\d))|;|\\quad|\n")


def _squashed(text: str) -> str:
    """Letters, digits and signs only: "27 a^{3} + 54 a^{2} b" and "27a^3 + 54a^2b" alike."""
    plain = re.sub(r"\\(?:text|mathrm|left|right)\b|\\[a-zA-Z]+", " ", text)
    plain = plain.replace(chr(0x2013), "-").replace(chr(0x2212), "-")
    return re.sub(r"[^0-9a-zA-Z+\-=*/]", "", plain).lower()


def answers_whole_question(question: str, answer: str) -> bool:
    """``answer`` is all ``question`` asks: no second reaction, every part answered, and
    one of its options when it gives some."""
    # Several reactions and an equation for an answer: options or parts to balance, never
    # one. Reactions a Hess's law question gives are its data.
    if len(_ARROW.findall(question)) >= 2 and _ARROW.search(answer):
        return False
    choices = labelled_choices(question)
    pieces = [piece for piece in _ANSWER_PIECES.split(answer) if piece.strip()]
    if not choices:
        return labelled_parts(question) <= max(len(pieces), 1)
    if _are_options(choices):
        # Short labels are options to pick ("a) 1 J b) 2 J c) 3 J") unless they ask for
        # things and the answer states a value for each: "Find: a) the time of flight b) the
        # range c) the final speed" answered "4.04 s; 80.8 m; 44.4 m/s" lost its card
        # (2026-11-01). A note or a unit line under one value is no second answer.
        stated = [piece for piece in pieces if _states_a_value(piece)]
        holds_values = any(_leading_value(choice) is not None for choice in choices)
        if holds_values or len(stated) < len(choices):
            return any(_same_choice(answer, choice) for choice in choices)
        return True
    # Parts: one piece of the answer for each ("v = 20 m/s; s = 100 m").
    return len(pieces) >= len(choices)


def _states_a_value(piece: str) -> bool:
    """``piece`` is one value: it opens with it ("80.8 m") or with its symbol ("x = 80.8 m").
    A clause about a value ("to 3 s.f.", "from h = 80 m") holds a number and states none."""
    sides = _RELATION.split(piece, maxsplit=1)
    if len(sides) == 1:
        return _leading_value(piece) is not None
    symbol = _MARKUP.sub("", sides[0]).split()
    return len(symbol) == 1 and _leading_value(sides[1]) is not None


def _are_options(choices: list[str]) -> bool:
    """Short labelled answers to pick from, not parts that each ask something."""
    return len(choices) >= 3 and all(len(c.split()) <= 8 and "?" not in c for c in choices)


def _same_choice(answer: str, choice: str) -> bool:
    """The answer states this option: its value (2% apart, "98 g/mol" for 98.07), or its
    words. An equation is no number."""
    chosen = _leading_value(choice)
    if chosen is not None:
        if _ARROW.search(answer):
            return False
        # The value as written after its last relation: "4.0 \\times 10^{2}" keeps its power
        # of ten, which a stripped right side lost ("4" matched the option "4 J").
        given = _leading_value(_RELATION.split(answer)[-1])
        return given is not None and abs(given - chosen) <= 0.02 * max(abs(chosen), 1e-9)
    plain_choice = _MARKUP.sub("", choice).lower().strip()
    return bool(plain_choice) and plain_choice in _MARKUP.sub("", answer).lower()


_FRACTION = re.compile(r"\\[dt]?frac\s*\{\s*(-?[\d.]+)\s*\}\s*\{\s*(-?[\d.]+)\s*\}")
_LEADING = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?"
    r"(?:\s*(?:\\times|\\cdot|\u00d7|\u00b7|x|\*)\s*10\s*\^\s*\{?\s*(-?\d+)\s*\}?)?"
)


def _leading_value(text: str) -> float | None:
    """The number a text opens with: "2 x 10^5 J", "\\frac{1}{2}", "78.54 cm²", "1/2"."""
    plain = _FRACTION.sub(r"\1/\2", text).replace("$", "").replace("\\,", "").replace(",", "")
    plain = plain.replace(chr(0x2212), "-")
    match = _LEADING.match(plain)
    if match is None:
        return None
    value = float(match.group(1))
    if match.group(2):
        value /= float(match.group(2)) or 1.0
    if match.group(3):
        # "1 x 10^1000" in an option is no number a card can match, never an error.
        exponent = int(match.group(3))
        if abs(exponent) > 300:
            return None
        value *= 10.0**exponent
    return value


def answers_with(question: str, verified: VerifiedSolveBlock, *, locale: str | None = None) -> bool:
    """A verified block may stand for ``question``: the readers read it, written by a user
    of ``locale``, and it answers what is asked or carries no answer line to judge (a
    diagram)."""
    if unreadable(question, locale) is not None:
        return False
    answer = verified.display_answer or verified.canonical_answer or ""
    return not answer or answers_the_question(question, answer)


def whole_question_fetch(
    question: str,
    fetched: SubjectFetch,
    *,
    locale: str | None = None,
    problems: tuple[str | None, ...] = (),
) -> SubjectFetch:
    """``fetched`` as it was, or without its verified result when the readers could not read
    ``question`` or an earlier ``problems`` line it solved (a follow-up's), or when that
    result answers part of ``question``."""
    verified = fetched.verified
    if verified is None and fetched.direct_text is None:
        return fetched
    if any(unreadable(text, locale) for text in (question, *problems) if text):
        return _DECLINED
    if verified is None or fetched.direct_text is not None:
        return fetched
    if answers_with(question, verified, locale=locale):
        return fetched
    return _DECLINED


_DECLINED = SubjectFetch(
    subject_block=None,
    verified=None,
    solver_unverified=False,
    unverified_subject=None,
    direct_text=None,
)
