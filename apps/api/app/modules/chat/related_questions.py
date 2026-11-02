"""Which turns get follow-up questions, and which of the model's candidates are kept.

``related_prompts`` asks the model and caches the result; this module holds the
rules on either side of that call, with no model and no Redis: whether a turn
continues a subject problem (``follow_up_thread``) or is a real general question
(``follow_up_topic``), and which candidate questions are short, on topic and new
(``accepted_questions``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.modules.chat.clarify_card import CLARIFY_FENCE
from app.modules.chat.follow_up_repeats import repeats_earlier
from app.modules.chat.follow_up_thread import subject_for_related, thread_problem
from app.modules.chat.follow_up_words import LATIN, STOP_WORDS, TOPIC_WORD, topic_words
from app.modules.turn_reading.personal import is_personal_disclosure_turn
from app.modules.turn_reading.routing import is_lightweight_chat_turn
from app.modules.turn_reading.writing_kind import writing_request_kind
from app.services.md_fence_scan import iter_fences, read_fence_marker
from app.services.text_normalize import collapse_ws, straighten_apostrophes

# Questions shown under a reply: three, or none.
MAX_QUESTIONS = 3
_ANSWER_CHARS = 800
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# "What if it was 5?" does not say what is 5: the 3, the right side, or x.
_VAGUE_WHAT_IF = re.compile(
    r"^what\s+if\s+(?:it|that|this|they)\s+(?:was|were|is|are)\s+[-+]?\d[\d.,]*\s*\??$",
    re.IGNORECASE,
)
# A word in any script: "Какой", "ዶሮ" and "pâte" count as words, not only ASCII.
_WORD = re.compile(r"[^\W\d_]{2,}")
_MATH_SPAN = re.compile(r"\$([^$\n]+)\$")
# A digit glued to a radical (`^5\sqrt{x}`) or to a variable (`x5`).
_GLUED_RADICAL = re.compile(r"\^\s*\d+\s*\\sqrt")
_GLUED_VARIABLE = re.compile(r"(?<![A-Za-z\\^_{])[A-Za-z]\d+")
_MIN_QUESTION_WORDS = 4
# One line on a phone, two at most: a follow-up is a tap, not a problem set.
_MAX_QUESTION_CHARS = 64
_MAX_QUESTION_WORDS = 12
# A general answer this short is a quick reply or a question back to the user.
_GENERAL_MIN_ANSWER_CHARS = 280
_GENERAL_MIN_QUESTION_WORDS = 3
_CONTENT_WORD = re.compile(rf"[{LATIN}]{{5,}}")
_UNIT_TOKEN = re.compile(r"[a-z]+/[a-z]+")


def _digit_skeleton(text: str) -> str:
    return _NUMBER.sub("#", collapse_ws(text).casefold())


def _folded_question(text: str) -> str:
    return collapse_ws(text).casefold().rstrip("?").strip()


def _prev_significant(text: str) -> str:
    stripped = text.rstrip()
    return stripped[-1] if stripped else ""


def _space_math_span(span: str) -> str:
    """Put a space on each side of = and of a binary + or -."""
    out: list[str] = []
    i = 0
    n = len(span)
    while i < n:
        ch = span[i]
        if ch == "\\":
            j = i + 1
            while j < n and span[j].isalpha():
                j += 1
            out.append(span[i:j])
            i = j
            continue
        if ch in "^_":
            if i + 1 < n and span[i + 1] == "{":
                depth = 0
                j = i + 1
                while j < n:
                    if span[j] == "{":
                        depth += 1
                    elif span[j] == "}":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                out.append(span[i:j])
                i = j
                continue
            out.append(ch)
            i += 1
            continue
        prev = _prev_significant("".join(out))
        binary = ch == "=" or (ch in "+-" and prev not in {"", "=", "+", "-", "*", "/", "(", "^"})
        if binary:
            if out and not "".join(out).endswith(" "):
                out.append(" ")
            out.append(f"{ch} ")
            i += 1
            while i < n and span[i] == " ":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out).strip()


_QUESTION_OPENER = re.compile(
    r"^(?:how|what|why|when|where|which|who|whose|can|could|should|would|is|are|do|does|"
    r"did|will)\b",
    re.IGNORECASE,
)


def _symbols_stay_apart(text: str) -> bool:
    for span in _MATH_SPAN.findall(text):
        if _GLUED_RADICAL.search(span) or _GLUED_VARIABLE.search(span):
            return False
    return True


def _visible_text(text: str) -> str:
    """What the phone shows: ``$\frac{1}{2}$`` reads as about four characters."""

    def _inner(match: re.Match[str]) -> str:
        return re.sub(r"\\[A-Za-z]+|[{}]", "", match.group(1))

    return collapse_ws(_MATH_SPAN.sub(_inner, text))


def _one_short_line(text: str) -> bool:
    """One question that fits a line or two, not a restated problem."""
    visible = _visible_text(text)
    if len(visible) > _MAX_QUESTION_CHARS or len(visible.split()) > _MAX_QUESTION_WORDS:
        return False
    # "A car travels 120 km in 2 h. What is its speed?" is a problem set,
    # not a tap. A decimal point (2.5) is not a sentence end.
    return re.search(r"[.!?:;]\s+\S", visible.rstrip("?")) is None


def _prepare_question(candidate: str) -> str | None:
    """A short full question with a variable and a number kept apart, or none."""
    cleaned = collapse_ws(candidate).strip("\"'“”")
    if not cleaned.endswith("?") and _QUESTION_OPENER.match(cleaned):
        # The model left off the mark ("why does everest grow taller"): the question is whole.
        cleaned = cleaned.rstrip(".") + "?"
    letter_words = _WORD.findall(cleaned)
    # A sum such as "What is 3 + 5?" is short, and it still names the problem.
    # "How" does not.
    short_with_number = _NUMBER.search(cleaned) is not None and len(letter_words) >= 2
    long_enough = len(letter_words) >= _MIN_QUESTION_WORDS or short_with_number
    if not cleaned.endswith("?") or not long_enough:
        return None
    if not _one_short_line(cleaned) or not _symbols_stay_apart(cleaned):
        return None

    def _spaced(match: re.Match[str]) -> str:
        return f"${_space_math_span(match.group(1))}$"

    return _MATH_SPAN.sub(_spaced, cleaned)


# "What if it took 10 s?" and "Why does that work?" point back at the
# problem instead of naming it; a short follow-up is allowed to.
_BACK_REFERENCE = re.compile(
    r"^(?:what|and) if\b|\b(?:it|its|it's|this|that|these|those|they|same|instead)\b",
    re.IGNORECASE,
)


def _keep_question(
    question: str,
    candidate: str,
    problem: str | None,
    anchors: set[str],
) -> bool:
    cleaned = collapse_ws(candidate)
    if _VAGUE_WHAT_IF.match(cleaned):
        return False
    if not cleaned:
        return False
    folded = cleaned.casefold()
    if _folded_question(cleaned) == _folded_question(question):
        return False
    if "suggestion" in folded:
        return False
    if _digit_skeleton(cleaned) == _digit_skeleton(question):
        return False
    if (
        problem is not None
        and problem != question
        and _folded_question(cleaned) == _folded_question(problem)
    ):
        return False
    # "3 + 4" has no long word. A follow-up that mentions neither 3 nor 4,
    # nor points back at the problem, left it.
    if anchors and not (_mentions_anchor(cleaned, anchors) or _BACK_REFERENCE.search(cleaned)):
        return False
    return True


def _problem_anchors(question: str) -> set[str]:
    folded = collapse_ws(question).casefold()
    numbers = set(_NUMBER.findall(folded))
    if not numbers:
        return set()
    # "Why convert km/h to m/s first?" names the problem by its unit.
    return numbers | set(_CONTENT_WORD.findall(folded)) | set(_UNIT_TOKEN.findall(folded))


def topic_anchors(question: str, reply: str) -> set[str]:
    """Words that keep a general follow-up on the user's topic.

    The question's words, and the topic words of the whole reply's prose: "Can I use
    whole wheat flour?" stays with a sourdough answer that mentions flour. The reply's
    first 800 characters and its five-letter words were too few: under a flat-tire answer
    "How do I jack up the car?" and "Do I need to torque the nuts?" were dropped
    (2026-10-29). Fillers ("good", "sure"), links and code are no topic. A question in a
    script without Latin letters has none, and the check stays off.
    """
    asked = {
        word
        for word in TOPIC_WORD.findall(collapse_ws(question).casefold())
        if word not in STOP_WORDS
    }
    if not asked:
        return set()
    return asked | topic_words(straighten_apostrophes(_reply_prose(reply)))


_LINK = re.compile(r"https?://\S+")


def _reply_prose(reply: str) -> str:
    """The reply without its fenced blocks and links."""
    kept, last = [], 0
    for fence in iter_fences(reply):
        kept.append(reply[last : fence.start])
        last = fence.end
    kept.append(reply[last:])
    return _LINK.sub(" ", "".join(kept))


def _mentions_anchor(follow_up: str, anchors: set[str]) -> bool:
    folded = collapse_ws(follow_up).casefold()
    # A reply's topic words are singular: "nut" anchors "the nuts".
    return any(re.search(rf"\b{re.escape(anchor)}s?\b", folded) for anchor in anchors)


def accepted_questions(
    question: str,
    raw: list[str],
    problem: str | None = None,
    anchors: set[str] | None = None,
    earlier: Sequence[str] = (),
) -> list[str]:
    """The candidates to show: short, on topic, and new to the chat. ``earlier`` is what
    it already asked: the user's earlier lines and the questions shown before."""
    if anchors is None:
        anchors = _problem_anchors(question)
        if problem is not None and problem != question:
            anchors |= _problem_anchors(problem)
    kept: list[str] = []
    for item in raw:
        prepared = _prepare_question(item)
        if prepared is None or not _keep_question(question, prepared, problem, anchors):
            continue
        if repeats_earlier(prepared, [*earlier, *kept]):
            continue
        kept.append(prepared)
        if len(kept) == MAX_QUESTIONS:
            break
    return kept


def answer_excerpt(answer: str) -> str:
    # The fence lines go; a code block's body reads as text.
    lines = [line for line in answer.split("\n") if read_fence_marker(line, lenient=True) is None]
    return collapse_ws(" ".join(lines).replace("```", " "))[:_ANSWER_CHARS]


# A line that asks for something to know: a question, or "explain", "tips for", "pros
# and cons of", "make me a plan". A draft is a writing request and gets none.
_ASKS_TO_KNOW = re.compile(
    r"^(?:how|what|what's|whats|why|when|where|which|who|whose|can|could|would|should|"
    r"is|are|was|were|do|does|did|will|explain|tell me|teach me|show me|give me|list|"
    r"compare|describe|summari[sz]e|recommend|suggest|help me|ideas?|tips?|best|"
    r"pros and cons|make me|plan (?:a|an|my|our|the|me)|create)\b",
    re.IGNORECASE,
)
# A reminder, a saved fact or a setting is done once it is done. "How do I
# remember vocabulary?" and "best to-do list app?" are questions, not commands.
_ADMIN_REQUEST = re.compile(
    r"\b(?:remind me|(?:set|make|create)(?: me)? (?:a |an )?(?:new )?(?:reminder|alarm|timer|to[- ]?do)|"
    r"remember (?:that|this|my|me)\b|"
    r"don'?t forget|(?:add|put)\b.{0,40}\bto my (?:to-?do|list|schedule|reminders)|"
    r"my settings|my preferences|turn (?:on|off)|switch (?:on|off)|call me)",
    re.IGNORECASE,
)
# Reading the To-do list back is admin too (2026-10-25: "ok last thing, what's on my to do
# list right now?" got what-ifs on a falling ball). Only by its own names: "what's in my
# list after this loop runs?", "what is my schedule c deduction?", "do i have due process
# rights?" and "What's the best to-do list app?" ask something else.
_TODO_LIST = (
    r"to[- ]?do(?:s| list)?|reminders?(?!\s+(?:app|settings))|"
    r"schedule (?:for )?(?:today|tonight|tomorrow|this week)"
)
_READS_OWN_LIST = re.compile(
    rf"\b(?:what|anything)(?:'?s|\s+(?:is|are|else|still|left|there))*\s+(?:on|in) my "
    rf"(?:{_TODO_LIST})\b|\b(?:show|list|read|check)(?: me)? my (?:{_TODO_LIST})\b|"
    rf"\bwhat(?:'?s| is| are) my (?:{_TODO_LIST})\b|"
    r"\bdo i have (?:any )?(?:to-?dos?|reminders?)\b|"
    r"\b(?:what|which|any) (?:reminders|to-?dos)\b(?!\s+(?:app|settings))",
    re.IGNORECASE,
)


def general_question(question: str, answer: str) -> bool:
    """A real question with a full answer, outside the subjects.

    Small talk, a personal update, a draft the user asked for, a reminder, a read
    of the To-do list or a setting, and a short reply get no follow-ups.
    Small talk that reads like a question ("how's your day?") gets a short reply,
    which the length check catches.
    """
    cleaned = collapse_ws(question)
    if len(cleaned.split()) < _GENERAL_MIN_QUESTION_WORDS:
        return False
    if not (cleaned.endswith("?") or _ASKS_TO_KNOW.match(cleaned)):
        return False
    if is_lightweight_chat_turn(cleaned) or is_personal_disclosure_turn(cleaned):
        return False
    if writing_request_kind(cleaned) is not None or _ADMIN_REQUEST.search(cleaned):
        return False
    if _reads_own_list(cleaned):
        return False
    return len(answer_excerpt(answer)) >= _GENERAL_MIN_ANSWER_CHARS


def _reads_own_list(text: str) -> bool:
    """A read of the To-do list, typed with the phone's curly apostrophe too."""
    return _READS_OWN_LIST.search(straighten_apostrophes(collapse_ws(text))) is not None


# A card the user answers with a tap is the reply's next step: a clarify card's
# picks, or a reminder to confirm. Follow-up questions under it would compete.
_AWAITS_A_TAP = frozenset({CLARIFY_FENCE, "reminder_proposal"})


def follow_up_topic(
    question: str,
    answer: str,
    prior: Sequence[Any] | None,
    *,
    allow_general: bool,
    shown: Sequence[str] | None = (),
) -> tuple[str, str | None] | None:
    """("subject", problem) or ("general", None); None makes no call.

    ``shown`` is what the chat offered under its last replies (None while not known): a
    line on a topic of its own continues a problem only when its reply still works it,
    and a tapped follow-up always does (``thread_problem``). A reply that ends on a card waiting for a tap has its follow-up already: a clarify
    card's questions, a reminder to confirm. Suggestions under it only repeated them
    ("What is your budget?"). A line that reads the To-do list back gets none.
    """
    if any(fence.lang in _AWAITS_A_TAP for fence in iter_fences(answer)):
        return None
    if _reads_own_list(question):
        # Nothing to dig into, and no follow-up of the problem before it.
        return None
    problem = thread_problem(question, prior, answer, shown)
    if problem is not None and (_has_quantity(problem) or not _asks(problem)):
        return "subject", problem
    if problem is not None and problem == question:
        # A subject question with nothing to change ("Who was Charles?", "Why kelvin?")
        # gets the topic's next questions, not "What if the temperature doubles?"; a line
        # after it ("do you have a picture of him?") is judged as any question is.
        return "general", None
    if allow_general and general_question(question, answer):
        return "general", None
    return None


def _has_quantity(problem: str) -> bool:
    """A number to change, or maths to vary: what a what-if is made of."""
    return _NUMBER.search(problem) is not None or subject_for_related(problem) == "math"


def _asks(question: str) -> bool:
    cleaned = collapse_ws(question)
    if not (cleaned.endswith("?") or _ASKS_TO_KNOW.match(cleaned)):
        return False
    return not (is_lightweight_chat_turn(cleaned) or is_personal_disclosure_turn(cleaned))
