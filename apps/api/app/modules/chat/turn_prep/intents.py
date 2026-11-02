"""Plan a turn: the separate requests one message holds, before anything answers it.

"I need a new laptop, and I also want to find remote backend engineering jobs" is
two requests: advice, and a live search. ``plan_turn`` cuts the message with the
text rules in ``clauses`` and labels each part with the classifier that already
owns that kind of request (settings, picture, photo, reminder, a STEM solve, a
live lookup), so the search gates, the tool loop and the settings and picture
paths each take their own part instead of reading the whole line as one.

No model is asked. The plan is regex over the user's words: a one-part message
(nearly every turn) stops after the splitter, and a multi-part one runs each
part's classifiers once (cached, since several gates ask). Formatting the reply
is not this module's job: the prompt renders the plan (``prompt_constants.multi_part``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from app.core.readings import reading
from app.modules.account.settings_intent import extract_settings_changes
from app.modules.chat.turn_prep.clauses import (
    Clause,
    Cut,
    leans_on_definite,
    points_back,
    request_body,
    request_clauses,
    without_connector,
)
from app.modules.images.gen_intent import extract_image_gen_prompt, stem_subject_claims
from app.modules.images.lookup_intent import extract_image_lookup_query
from app.modules.turn_reading.plan import (
    HANDLED_KINDS,
    PartKind,
    TurnPart,
    TurnPlan,
    single_plan,
)
from app.modules.web_search import asks_about_a_place, is_distance_query
from app.modules.web_search.detection import needs_web_search
from app.services.subjects.dispatch import detect_subject

# After a sentence or comma, two open questions need this many words of their own.
_MIN_OWN_TOPICS = 2
# Requests whose path decides them alone: what follows one is not a follow-up to it.
_OWNED_KINDS: frozenset[PartKind] = frozenset({"settings", "image", "photo", "reminder", "solve"})
_PLAN_CACHE = 256
_REMINDER = re.compile(
    r"^(?:remind me|set (?:a |an )?(?:reminder|alarm)|add (?:a )?(?:reminder|todo|to-do))\b",
    re.IGNORECASE,
)
# A calculation asked of the problem just stated: "find the total current", "work out
# how fast it lands". "Find me a book" is a request of its own.
_WORKS_ON_PROBLEM = re.compile(
    r"^(?:then\s+)?(?:find(?!\s+(?:me|us)\b)|calculate|compute|determine|work\s+out|"
    r"evaluate|estimate|how\s+(?:fast|far|long|high|deep|tall))\b",
    re.IGNORECASE,
)


def part_kind(text: str, *, chemistry_enabled: bool = True) -> PartKind:
    """Which existing path owns this request, read with that path's own rules."""
    body = request_body(text)
    if extract_settings_changes(body):
        return "settings"
    if extract_image_lookup_query(body):
        return "photo"
    stem = stem_subject_claims(body, chemistry_enabled=chemistry_enabled)
    if not stem and extract_image_gen_prompt(body):
        return "image"
    if _REMINDER.match(body):
        return "reminder"
    if stem or detect_subject(body, chemistry_enabled=chemistry_enabled) is not None:
        return "solve"
    if needs_web_search(body):
        return "live"
    return "ask"


def _continues_solve(
    clause: Clause, kind: PartKind, last: Clause, last_kind: PartKind, *, chemistry_enabled: bool
) -> bool:
    """ "Two 3 Ω resistors in parallel across 9 V, and find the total current": a
    calculation with no numbers of its own needs the physics givens before it. Solved
    apart, the first half's parallel resistance answered a question about the current.
    A physics solve reads its asked quantity from the whole question; a maths command
    ("graph y = x^2") is its own request."""
    body = request_body(clause.text)
    return (
        last_kind == "solve"
        and kind == "ask"
        and _WORKS_ON_PROBLEM.match(body) is not None
        and not any(ch.isdigit() for ch in body)
        and detect_subject(request_body(last.text), chemistry_enabled=chemistry_enabled)
        == "physics"
    )


def _keeps_cut(
    clause: Clause, kind: PartKind, last: Clause, last_kind: PartKind, *, chemistry_enabled: bool
) -> bool:
    """A strong cut stands. A weaker one never splits one subject ("the weather in Paris
    and the best museum in Paris"), nor a physics problem from what it asks. It
    stands for a request another path owns, or an open question after one ("switch to
    dark mode and tell me a joke"). Two open questions need a sentence or comma between
    them and a later one that stands on its own words: "what should I pack" and "who
    scored the goals" lean on the question before."""
    if clause.cut == Cut.STRONG:
        return True
    if clause.topics & last.topics or _continues_solve(
        clause, kind, last, last_kind, chemistry_enabled=chemistry_enabled
    ):
        return False
    if kind != last_kind and (kind != "ask" or last_kind in _OWNED_KINDS):
        return True
    if clause.cut == Cut.AND:
        return False
    return len(clause.topics) >= _MIN_OWN_TOPICS and not leans_on_definite(clause.text)


@reading(declined=lambda text, **_: single_plan(text))
@lru_cache(maxsize=_PLAN_CACHE)
def plan_turn(text: str, *, chemistry_enabled: bool = True) -> TurnPlan:
    """The separate requests in ``text``, in order; one part when it asks one thing."""
    split = request_clauses(text)
    if len(split.clauses) < 2:
        return single_plan(text)
    problem = _Problem.of(split.context, split.clauses, chemistry_enabled=chemistry_enabled)
    merged: list[tuple[Clause, PartKind]] = []
    for clause in split.clauses:
        kind = problem.kind(clause)
        if (
            not merged
            or problem.separate_questions(merged[-1][0], clause)
            or _keeps_cut(clause, kind, *merged[-1], chemistry_enabled=chemistry_enabled)
        ):
            merged.append((clause, kind))
            continue
        last, _ = merged.pop()
        joined = Clause(f"{last.text} {clause.text}", last.cut, last.topics | clause.topics)
        merged.append((joined, problem.kind(joined)))
    if len(merged) < 2:
        return single_plan(text)
    parts = tuple(problem.part(clause, kind) for clause, kind in merged)
    # The setup opens each question it belongs to; a part it does not open keeps it as the
    # plan's context.
    every = problem.setup is not None and all(problem.carries(clause) for clause, _ in merged)
    return TurnPlan(parts, context="" if every else split.context)


@dataclass(frozen=True)
class _Problem:
    """The problem the statements before the first question set up, and its subject.

    "A ball is dropped from 20 m. What is its speed after 1 s? How long does it take to
    reach the ground?" states its givens once and asks two questions. Cut apart, the
    second lost the ball, read as a trip from the user, and searched. Each question about
    the problem carries the setup and is read with it (``carries``), so it stays that
    subject's homework; "I'm a backend dev" sets up no problem.
    """

    setup: str | None
    subject: str | None
    chemistry_enabled: bool

    @classmethod
    def of(cls, context: str, clauses: Sequence[Clause], *, chemistry_enabled: bool) -> _Problem:
        """A setup by its own reading: its own subject, and givens (a quantity, or an object
        a question points back to). A later question never lends it a subject: "I'm a
        backend dev. … What is 12 squared?" and "We're in Paris. How far is 300 m in feet?"
        set up nothing."""
        subject = detect_subject(context, chemistry_enabled=chemistry_enabled) if context else None
        givens = any(ch.isdigit() for ch in context) or any(
            points_back(clause.text) for clause in clauses
        )
        if subject is None or not givens:
            return cls(None, None, chemistry_enabled)
        setup = context if context.endswith((".", "!", "?", ":")) else f"{context}."
        return cls(setup, subject, chemistry_enabled)

    def carries(self, clause: Clause) -> bool:
        """Whether a question is about the problem: the subject claims it with the setup
        before it, and nothing of its own words sends it elsewhere. They do when it follows
        a strong cut ("Also, …"), another path owns it (a setting, a picture, a photo, a
        reminder), it asks about a place or the weather, it is live by a cue of its own
        (news, prices, scores; "how long does it take to reach the ground" is no trip
        without the setup), or another subject claims it."""
        if self.setup is None or clause.cut == Cut.STRONG:
            return False
        body = request_body(clause.text)
        alone = part_kind(body, chemistry_enabled=self.chemistry_enabled)
        if alone in HANDLED_KINDS or alone == "reminder":
            return False
        own = detect_subject(body, chemistry_enabled=self.chemistry_enabled)
        if own is not None:
            return own == self.subject
        if asks_about_a_place(body) or (needs_web_search(body) and not is_distance_query(body)):
            return False
        joined = detect_subject(f"{self.setup} {body}", chemistry_enabled=self.chemistry_enabled)
        return joined == self.subject

    def separate_questions(self, last: Clause, clause: Clause) -> bool:
        """Two questions about the problem, each its own sentence: each is solved with the
        setup before it ("How high does it go? How long does it take to reach the top?").
        "Give your answer as a fraction" shapes the answer; it asks nothing."""
        return (
            clause.cut >= Cut.SENTENCE
            and _asks(last)
            and _asks(clause)
            and self.carries(last)
            and self.carries(clause)
        )

    def kind(self, clause: Clause) -> PartKind:
        """The clause's kind: read with the setup when its own words read as live, a lookup
        it only seemed to be without its givens, and it is about the problem."""
        alone = part_kind(clause.text, chemistry_enabled=self.chemistry_enabled)
        if alone == "live" and self.carries(clause):
            return part_kind(
                f"{self.setup} {clause.text}", chemistry_enabled=self.chemistry_enabled
            )
        return alone

    def part(self, clause: Clause, kind: PartKind) -> TurnPart:
        """The request as its readers take it: a question about the problem with the setup
        before it, and read with it."""
        text = _quoted(clause.text)
        if not self.carries(clause):
            return TurnPart(text, kind)
        joined = f"{self.setup} {text}"
        return TurnPart(joined, part_kind(joined, chemistry_enabled=self.chemistry_enabled))


def _asks(clause: Clause) -> bool:
    return clause.text.rstrip().endswith("?")


def cuts_after_picture(text: str, is_picture: Callable[[str], bool]) -> bool:
    """Whether ``plan_turn`` cuts ``text`` after a first part that is a picture: "draw me a
    cat and also explain black holes", "draw me a cat. Also, what is the capital of
    France?", "draw me a cat and suggest names". The picture reader asks this before it
    draws the whole line, so the line is drawn whole exactly where the plan keeps it whole.

    The same clause and cut rules as ``plan_turn``, with ``is_picture`` (the picture
    reader's own, on a request's body) for ``part_kind``: after a picture, every other
    kind of request cuts alike, and the reader must not ask the SymPy-backed readings
    on the event loop.
    """

    def kind(clause: Clause) -> PartKind:
        return "image" if is_picture(request_body(clause.text)) else "ask"

    clauses = request_clauses(text).clauses
    if len(clauses) < 2 or kind(clauses[0]) != "image":
        return False
    last = clauses[0]
    for index, clause in enumerate(clauses[1:], start=1):
        if _keeps_cut(clause, kind(clause), last, "image", chemistry_enabled=True):
            return True
        if index == len(clauses) - 1:
            return False
        last = Clause(f"{last.text} {clause.text}", last.cut, last.topics | clause.topics)
        if kind(last) != "image":
            return False
    return False


def _quoted(text: str) -> str:
    """The request as a reader would quote it: no leading "and also", no "I also want"."""
    return re.sub(r"\b(i|we) also\b", r"\1", without_connector(text), flags=re.IGNORECASE)
