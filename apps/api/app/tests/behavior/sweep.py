"""Hundreds of real-sounding turns through routing and post-processing.

Each corpus entry (``sweep_corpus/*.json``) is a user message, a reply a model
might write, and what should happen. A turn is routed with the real turn path
(as the battery does), then its reply goes through the real finalize step,
with reminder and settings logic over in-memory stores. Every turn
where a rule hijacked, replaced or mangled it is listed.

    uv run python -m app.tests.behavior.sweep [--only id,id] [--area writing] [--show]

The sweep models production, so a maths decline stays silent; ``RECALL_STRICT_DECLINES=1``
in front raises the programming errors a decline would hide (``math/solve/declines.py``).

``expect`` per entry: "answer" (an ordinary reply that must reach the user),
"instant" (the server answers without the model: the date, the time),
"photo", "search", "image_gen", "save" (a reminder is saved), "ask_time",
"change" (done / delete / move), "read" (the reminder list), "settings",
"memory", "todo" (any of the reminder outcomes), "todo_screen" (a to-do change asked in
another language: nothing saved or changed, the Open To-do button instead). A list asks
for every outcome on the one turn: ``["search", "answer"]`` is a message with a live part
and another
answered beside it ("image_gen" and "settings" there are the picture or card a
multi-part reply carries). Area "multi" must be read as more than one request and
"multi lookalike" as one.

Turns run as a Pro user, so image generation can claim one; ``"pro": false``
runs one as free. ``"location"`` gives the user a saved location. ``"gap"``
names a known miss: ``test_sweep.py`` expects it to fail until it is fixed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models.orm import User
from app.modules.account.settings_intent import extract_settings_changes
from app.modules.chat.chart_sanitize import chart_is_drawable
from app.modules.chat.finalize_passes import enrich_final_content
from app.modules.chat.turn_deps import default_deps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.conversation import messages_repository
from app.modules.memory import is_explicit_memory_command
from app.modules.todos import write_log
from app.modules.todos.reply_check import NEED_A_TIME
from app.modules.turn_reading.routing import EMOJI
from app.services.md_fence_scan import iter_closed_fences, without_fences
from app.tests.behavior.cases import Case, Expect
from app.tests.behavior.harness import USER_TIMEZONE, battery_settings, route_case
from app.tests.fakes import fake_session

CORPUS = Path(__file__).with_name("sweep_corpus")

# Replies the server writes in place of the model's when it decides a turn was
# about reminders. On an ordinary turn any of them is a hijack.
CANNED = (
    NEED_A_TIME,
    "That time already passed.",
    "I didn't change your reminders.",
    "I didn't set a reminder.",
    "Could not ",
    "Couldn't find",
    "I couldn't find",
    "You have no reminders",
    "No reminders",
)
TODO_EXPECTS = {"save", "ask_time", "change", "read", "todo"}
EXPECTS = {
    "answer",
    "instant",
    "photo",
    "search",
    "image_gen",
    "settings",
    "memory",
    "todo_screen",
    *TODO_EXPECTS,
}
# Areas whose turns never need the live web.
NO_SEARCH_AREAS = {
    "math", "physics", "chemistry", "writing", "code", "chitchat", "statement", "made data",
    "search capability",
}  # fmt: skip
# Asks nothing to look up ("great job today", "teach me something today", "give me
# sample CSV data"): not even a model round that may choose to search.
# Works on the chat itself ("Yes" to "Does that make sense?", "give me a practice problem",
# "summarize what we covered"): a search wrapped these in unrelated pages.
# "Can you search the web?" asks what Recall does: a search took the line before it.
NO_SEARCH_ROUND_AREAS = {"statement", "made data", "chat bound", "search capability"}
# Turns that answer the clarify card before them: they never ask again.
AFTER_CARD_AREAS = {"clarify answer"}
STEM_AREAS = {"math", "physics", "chemistry"}
# Messages with separate requests, and look-alikes that are one request.
MULTI_AREAS = {"multi"}
SINGLE_PART_AREAS = {"multi lookalike"}
# Everyday messages that use a maths word ("differentiate between weather and
# climate", "simplify it" about an essay), or that sound like a follow-up to the
# physics or chemistry problem before them ("in french please", "what about the
# party?"), or that burn or react without a reaction to work ("i burned my hand on
# the stove", "what happens when sodium reacts with water"). None of them is solved.
NOT_MATH_AREAS = {"math lookalike", "followup lookalike", "chemistry lookalike"}
# Look-alikes of a rule that reads the user's words: "good morning, what's the capital of
# Peru?" is a question, not an opener. The hint that rule adds must not be in the prompt.
LOOKALIKE_HINTS = {
    "opener lookalike": "compact",
    "correction lookalike": "correction",
    "detail lookalike": "detail",
    "continue lookalike": "continue",
    "chart lookalike": "chart",
    # A sentence with a few numbers in it, or a list that asks something.
    "numbers lookalike": "shared_numbers",
    # A question of its own after a reply, not "What?" at it.
    "missed lookalike": "reply_missed",
    "quiz lookalike": "quiz",
    "checklist lookalike": "checklist",
    # "Label: value" lines with no card before them are not picks.
    "clarify lookalike": "clarify_picks",
    # "The best countries for business" says what it is for: answered, not asked.
    "purpose given": "clarify",
    # A "hi" after a question is a new greeting, not one more of a run.
    "greeting lookalike": "greeting_again",
    "money lookalike": "money",
    # Someone's own money, advice, a choice, or a number the app assumed: the short reply.
    "money everyday": "money_worked",
    # "thanks" or "how do I bake bread?" after a loan's card is not about the loan.
    "money standing lookalike": "money_standing",
    # A money follow-up the server leaves to the model: a new price, a percent down, a card
    # payment, a deposit or a kind ("what if I put 20% down?"), or a bare amount beside a
    # price that may be the loan or the down payment. It works terms, rates and sums down.
    "money declined": "money",
    # "I don't understand why she left" is not a topic to be taught.
    "walkthrough lookalike": "walkthrough",
    # "My resume got rejected, what am I doing wrong?" asks for advice, not a résumé.
    "record lookalike": "personal_record",
    # "Should I tell my boss I'm pregnant?" asks for advice, not a message to send.
    "draft lookalike": "email",
}
# A loan, card or savings ask, or a what-if that changes the one before it ("what if i only
# do 3 years instead"): the server works its numbers, so the turn carries the money block.
MONEY_AREAS = {"money", "money lesson", "money everyday"}
# A lesson's money problem whose every number is the question's: laid out for the student.
MONEY_LESSON_AREAS = {"money lesson"}
# The answer to a whole exercise in a textbook's own form has no emoji at any setting; a
# message that only looks like one (a tip with 🍕, a conversion, a trip) keeps the setting.
EMOJI_FREE_AREAS = {"emoji homework"}
EMOJI_KEPT_AREAS = {"emoji lookalike"}
# A "yes" or "what about 15 years?" about the chat's earlier loan that no card answers: the
# model reads the loan's figures, worked by the app.
MONEY_STANDING_AREAS = {"money standing"}
# Reminders already saved, so "mark call mom as done" has something to find.
SEEDED = ("call mom", "dentist appointment", "gym", "pay rent", "read", "water the plants")


@dataclass(frozen=True)
class Entry:
    id: str
    area: str
    prompt: str
    reply: str
    expect: str = "answer"
    history: tuple[tuple[str, str], ...] = ()
    pro: bool = True
    location: str | None = None
    gap: str | None = None
    # More outcomes the same turn must also have (``"expect": ["search", "answer"]``).
    also: tuple[str, ...] = ()

    @property
    def expects(self) -> tuple[str, ...]:
        return (self.expect, *self.also)


@dataclass
class Outcome:
    entry: Entry
    final: str = ""
    route: Any = None
    saved: list[dict[str, Any]] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    settings_changes: Any = None
    memory_command: bool = False
    problems: list[str] = field(default_factory=list)


def load(paths: list[Path] | None = None) -> list[Entry]:
    entries: list[Entry] = []
    for path in paths or sorted(CORPUS.glob("*.json")):
        for raw in json.loads(path.read_text(encoding="utf-8")):
            history = tuple(
                (str(pair[0]), str(pair[1]))
                for pair in raw.get("history") or []
                if len(pair) == 2 and pair[1]
            )
            expects = raw.get("expect") or "answer"
            first, *also = [expects] if isinstance(expects, str) else expects
            entries.append(
                Entry(
                    id=str(raw["id"]),
                    area=str(raw.get("area") or path.stem),
                    prompt=str(raw["prompt"]),
                    reply=str(raw.get("reply") or ""),
                    expect=str(first),
                    history=history,
                    pro=bool(raw.get("pro", True)),
                    location=raw.get("location"),
                    gap=raw.get("gap"),
                    also=tuple(str(item) for item in also),
                )
            )
    return entries


@asynccontextmanager
async def _session() -> Any:
    yield fake_session()


def _user(*, pro: bool) -> User:
    return User(
        id=uuid4(),
        name="Bini",
        email="bini@example.com",
        plan="pro" if pro else "free",
        response_tone="casual",
        emoji_use="some",
        locale="en",
        timezone=USER_TIMEZONE,
        memory_enabled=True,
    )


@contextmanager
def _stores(outcome: Outcome, user: User) -> Iterator[None]:
    """In-memory reminders: six saved ones, and a record of every write."""
    items = [
        SimpleNamespace(
            id=uuid4(),
            user_id=user.id,
            content=title,
            topic="Reminders",
            due_at=datetime(2026, 10, 20, 15, 0, tzinfo=UTC),
            recurrence_rule=None,
            checked=False,
            chat_id=None,
            sort_order=index,
            notification_sent_at=None,
            email_sent_at=None,
            source="chat",
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
            updated_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
        for index, title in enumerate(SEEDED)
    ]

    async def list_for_user(*_args: Any, **_kwargs: Any) -> list[Any]:
        return list(items)

    # Like the real repository, a write made while the turn records (the
    # reminder card the user taps) is planned, not made.
    async def create(_session: Any, **kwargs: Any) -> Any:
        outcome.saved.append(kwargs)
        fields = {"checked": False, "sort_order": 0, "source": "chat", **kwargs}
        item = SimpleNamespace(id=uuid4(), **fields)
        planned = write_log.planned()
        if planned is not None:
            return write_log.plan_create(planned, item)  # type: ignore[arg-type]
        items.append(item)
        return item

    async def update(_session: Any, item: Any, **fields: Any) -> Any:
        outcome.changed.append(f"update {getattr(item, 'content', '?')} {sorted(fields)}")
        planned = write_log.planned()
        if planned is not None:
            return write_log.plan_update(planned, item, fields)
        for key, value in fields.items():
            setattr(item, key, value)
        return item

    async def delete_by_id(_session: Any, todo_id: Any, *_args: Any, **_kwargs: Any) -> bool:
        outcome.changed.append(f"delete {todo_id}")
        planned = write_log.planned()
        if planned is not None:
            row = next((item for item in items if item.id == todo_id), None)
            return write_log.plan_delete(planned, todo_id, row)
        return True

    repo = "app.modules.todos.repository"
    with ExitStack() as stack:
        for name, value in (
            ("list_for_user", list_for_user),
            ("create", create),
            ("update", update),
            ("delete_by_id", delete_by_id),
            ("get_open_dated_duplicate", AsyncMock(return_value=None)),
        ):
            stack.enter_context(patch(f"{repo}.{name}", value))
        yield


async def _inline(fn: Any, *args: Any, **_kwargs: Any) -> Any:
    return fn(*args)


# 09:00 in Nairobi on a Wednesday: every "tonight" and "at 6pm today" in the
# corpus is still ahead. On the real clock those turns failed whenever the
# suite ran after 16:00 UTC.
SWEEP_NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
# The real class, under a name the frozen clock leaves alone. Imported as
# app.tests.behavior.sweep (under pytest), this module's own ``datetime`` is
# frozen too: a check against that name skipped every module imported after
# this one, and the isinstance hook below recursed.
_REAL_DATETIME = datetime


class _AnyDateTime(type):
    """``isinstance(value, datetime)`` stays true for a real datetime.

    Patched in, the class replaces ``datetime`` in every check a module makes,
    and a JSON encoder that asked "is this a datetime?" of a real one said no.
    """

    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, _REAL_DATETIME)


class _SweepDateTime(datetime, metaclass=_AnyDateTime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return SWEEP_NOW.astimezone(tz) if tz is not None else SWEEP_NOW.replace(tzinfo=None)


@contextmanager
def frozen_clock() -> Iterator[None]:
    """Every app module that reads the time with ``datetime.now`` reads SWEEP_NOW."""
    with ExitStack() as stack:
        for name, module in list(sys.modules.items()):
            if name.startswith("app.") and getattr(module, "datetime", None) is _REAL_DATETIME:
                stack.enter_context(patch.object(module, "datetime", _SweepDateTime))
        yield


async def run_entry(entry: Entry) -> Outcome:
    with frozen_clock():
        return await _run_entry(entry)


async def _run_entry(entry: Entry) -> Outcome:
    outcome = Outcome(entry=entry)
    settings = battery_settings()
    outcome.route = await route_case(
        Case(
            entry.id,
            entry.area,
            entry.prompt,
            Expect(),
            "",
            history=entry.history,
            pro=entry.pro,
            location=entry.location,
        ),
        settings,
    )
    prior = entry.history[-1][1] if entry.history and entry.history[-1][0] == "assistant" else None
    outcome.settings_changes = extract_settings_changes(entry.prompt, prior_assistant=prior)
    outcome.memory_command = bool(is_explicit_memory_command(entry.prompt))

    user = _user(pro=entry.pro)
    deps = replace(
        default_deps(),
        session_factory=_session,
        users=SimpleNamespace(get_by_id=AsyncMock(return_value=user)),
    )
    rows = [SimpleNamespace(role=role, content=text) for role, text in entry.history]
    ctx = StreamContext(
        user_id=user.id,
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[
            *({"role": role, "content": text} for role, text in entry.history),
            {"role": "user", "content": entry.prompt},
        ],
        run_title=False,
        user_message_content=entry.prompt,
        reserved_tokens=0,
        max_output_tokens=0,
        user_timezone=USER_TIMEZONE,
        user=user,
        # A multi-part message's settings card, as the turn's prompt build made it.
        settings_card=outcome.route.settings_card or None,
        after_card=outcome.route.after_card,
    )
    with (
        _stores(outcome, user),
        patch("app.core.sympy_executor.run_sympy", _inline),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(
                return_value=[
                    *rows,
                    SimpleNamespace(role="user", content=entry.prompt),
                ]
            ),
        ),
    ):
        outcome.final = await enrich_final_content(
            deps,
            AsyncMock(),
            settings,
            ctx,
            assistant_text=entry.reply,
            usage={},
            outcome=TurnOutcome(),
            was_cancelled=False,
            assistant_parts=[entry.reply],
            should_cancel=None,
        )
    outcome.problems = (
        judge(outcome) + claims_above_a_pending_card(outcome.final) + undrawn_charts(outcome.final)
    )
    return outcome


_WS = re.compile(r"\s+")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W_]{3,}", text.lower()))


def _kept(reply: str, final: str) -> bool:
    """Most of the reply's words survived (layout fixes may move them)."""
    if not reply.strip():
        return True
    words = _words(reply)
    if not words:
        return _WS.sub("", reply) in _WS.sub("", final)
    return len(words & _words(final)) >= 0.8 * len(words)


def judge(outcome: Outcome) -> list[str]:
    """Every way the turn missed one of its expected outcomes, each named once."""
    entry, route = outcome.entry, outcome.route
    problems: list[str] = []
    for expect in entry.expects:
        problems.extend(p for p in _judge_expect(outcome, expect) if p not in problems)
    # The turn after a clarify card answers: another card, or its questions as prose, is
    # asking again (live: "plan my week", picks sent, a second card came back).
    if entry.area in AFTER_CARD_AREAS and "```clarify" in outcome.final:
        problems.append("asked with a card again")
    if entry.area in AFTER_CARD_AREAS and "?" in outcome.final:
        problems.append("asked a question again")
    if entry.area in MULTI_AREAS and "multi_intent" not in route.hints:
        problems.append("not read as more than one request")
    if entry.area in SINGLE_PART_AREAS and "multi_intent" in route.hints:
        problems.append("split into separate requests")
    return problems


def _judge_expect(outcome: Outcome, expect: str) -> list[str]:
    entry, route, final = outcome.entry, outcome.route, outcome.final
    problems: list[str] = []
    expects = set(entry.expects)
    canned = next((text for text in CANNED if final.strip().startswith(text)), None)

    if expect in {"answer", "photo", "search", "image_gen", "settings", "memory"}:
        if canned:
            problems.append(f"reply replaced by {canned!r}")
        elif not _kept(entry.reply, final) and entry.area not in AFTER_CARD_AREAS:
            # After a card, losing the model's second card is the point.
            problems.append("reply lost most of its words")
        # A reminder the entry also expects is the other part of the same turn.
        if outcome.saved and not expects & TODO_EXPECTS:
            problems.append(f"saved a reminder {outcome.saved[0].get('content')!r}")
        if outcome.changed and not expects & TODO_EXPECTS:
            problems.append(f"changed reminders: {outcome.changed[0]}")
    if expect == "answer":
        if route.photo:
            problems.append(f"photo lookup took the turn ({route.photo!r})")
        if route.image_gen:
            problems.append("image generation took the turn")
        if route.instant == "text" and route.instant_text:
            problems.append(f"instant reply: {route.instant_text[:80]!r}")
        # "How many minutes in a good nap" answered "Turn on Location".
        if route.instant == "location":
            problems.append("answered with the turn-on-location reply")
        # "3 cups of flour for 12 cookies…" is a problem to solve, not a pick to personalise.
        if entry.area in STEM_AREAS and "advice" in route.hints:
            problems.append("given the personal-recommendation hint")
        if (outcome.settings_changes or route.settings_card) and "settings" not in expects:
            problems.append(f"read as a settings change: {outcome.settings_changes}")
        if outcome.memory_command:
            problems.append("read as a memory command")
        if entry.area in NO_SEARCH_AREAS and route.search == "yes":
            problems.append("searched the web")
        elif entry.area in NO_SEARCH_ROUND_AREAS and route.search == "ask":
            problems.append("let the model decide to search")
        if entry.area in NOT_MATH_AREAS and (route.subject == "math" or route.solved):
            problems.append(f"read as maths (solved={route.solved})")
        unwanted = LOOKALIKE_HINTS.get(entry.area)
        if unwanted and unwanted in route.hints:
            problems.append(f"given the {unwanted!r} hint")
        if entry.area in MONEY_AREAS and "money" not in route.hints:
            problems.append("numbers not worked by the server (no money block)")
        if entry.area in MONEY_LESSON_AREAS and "money_worked" not in route.hints:
            problems.append("a lesson's money problem not laid out for the student")
        if entry.area in EMOJI_FREE_AREAS and EMOJI.search(final):
            problems.append("emoji left in a textbook exercise's answer")
        if entry.area in EMOJI_KEPT_AREAS and EMOJI.search(entry.reply) and not EMOJI.search(final):
            problems.append("emoji the user's setting keeps were removed")
        if entry.area in MONEY_STANDING_AREAS and "money_standing" not in route.hints:
            problems.append("the earlier loan's figures not given")
    elif expect == "instant" and not route.instant:
        problems.append("no instant reply")
    elif expect == "photo" and not route.photo:
        problems.append("no photo lookup")
    elif expect == "search" and route.search == "no":
        problems.append("no web search")
    elif expect == "image_gen" and not (route.image_gen or route.picture):
        problems.append("no image generation")
    elif expect == "settings" and not (outcome.settings_changes or route.settings_card):
        problems.append("not read as a settings change")
    elif expect == "memory" and not outcome.memory_command:
        problems.append("not read as a memory command")
    elif expect == "todo_screen":
        # The server answers a change asked in another language itself (an instant reply).
        if "```todo_link" in route.instant_text:
            final = route.instant_text
        if outcome.saved or outcome.changed:
            problems.append("changed reminders from a message in another language")
        if canned:
            problems.append(f"reply replaced by {canned!r}")
        if "```todo_link" not in final:
            problems.append(f"no Open To-do button (reply: {final[:70]!r})")
        elif not without_fences(final).strip():
            problems.append("an Open To-do button with no line saying what it is for")
    elif expect == "save" and not outcome.saved:
        problems.append(f"no reminder saved (reply: {final[:70]!r})")
    elif expect == "ask_time" and (outcome.saved or "?" not in final):
        problems.append(f"did not ask for a time (reply: {final[:70]!r})")
    elif expect == "change" and not outcome.changed and not canned:
        problems.append(f"no reminder changed (reply: {final[:70]!r})")
    elif expect == "read" and not ("call mom" in final.lower() or "reminder" in final.lower()):
        problems.append(f"did not read the reminders (reply: {final[:70]!r})")
    if expect in TODO_EXPECTS and route.photo:
        problems.append(f"photo lookup took the turn ({route.photo!r})")
    return problems


# Said above a reminder card nobody has tapped: nothing is saved yet. "The
# meeting is set for Friday" and "I set aside time to write" are not claims.
_PENDING_CARD_CLAIM = re.compile(
    r"\b(?:i['\u2019]ve set|i have set|i set (?:a|an|the|your|up|it)\b"
    r"|i['\u2019]ve (?:added|scheduled|saved|created)\b"
    r"|(?:reminder|it|that)(?:['\u2019]s| is| has been) (?:all )?set\b|reminder set\b"
    r"|i['\u2019]ll remind you|i will remind you|you['\u2019]ll (?:get|receive) a (?:reminder|notification)"
    r"|added (?:it |that )?to your (?:reminders|to-?dos?|list)"
    r"|got it (?:all )?set\b|you['\u2019]re all set for\b"
    r"|(?:i['\u2019]m |^\W*)(?:setting|adding|saving|scheduling) (?:that|the|your|a|it)\b)"
    r"|^\W*(?:done|all set)\b",
    re.IGNORECASE | re.MULTILINE,
)


def undrawn_charts(final: str) -> list[str]:
    """A ```chart the phone cannot draw ("Could not render that chart") never ships."""
    return [
        "a chart the phone cannot draw"
        for _start, _end, body in iter_closed_fences(final, "chart")
        if not chart_is_drawable(body)
    ]


def claims_above_a_pending_card(final: str) -> list[str]:
    """A reply carrying an untapped reminder card makes no completed-action claim."""
    if "```reminder_proposal" not in final or '"status": "saved"' in final:
        return []
    prose = re.sub(r"```.*?```", " ", final, flags=re.DOTALL)
    claim = _PENDING_CARD_CLAIM.search(prose)
    return [f"claims the change before the tap: {claim.group(0)!r}"] if claim else []


async def run(entries: list[Entry]) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for entry in entries:
        try:
            outcomes.append(await run_entry(entry))
        except Exception as exc:  # A crash is a finding too.
            outcomes.append(Outcome(entry=entry, problems=[f"crashed: {exc!r}"]))
    return outcomes


def report(outcomes: list[Outcome], *, show: bool = False) -> str:
    lines: list[str] = []
    bad = [outcome for outcome in outcomes if outcome.problems]
    by_area: dict[str, list[int]] = {}
    for outcome in outcomes:
        tally = by_area.setdefault(outcome.entry.area, [0, 0])
        tally[0] += 1
        tally[1] += bool(outcome.problems)
    lines.append(f"{len(outcomes)} turns, {len(bad)} with problems")
    for area, (total, failing) in sorted(by_area.items()):
        lines.append(f"  {area:<12} {failing:>3} / {total}")
    for outcome in bad:
        entry = outcome.entry
        lines.append(f"\n[{entry.id}] ({entry.area}, expect {entry.expect}) {entry.prompt!r}")
        for problem in outcome.problems:
            lines.append(f"  - {problem}")
        if show:
            lines.append(f"  final: {outcome.final[:200]!r}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated entry ids")
    parser.add_argument("--area", help="one area")
    parser.add_argument("--file", action="append", type=Path, help="corpus file(s)")
    parser.add_argument("--show", action="store_true", help="print each failing final reply")
    args = parser.parse_args()
    entries = load(args.file)
    if args.only:
        wanted = {item.strip() for item in args.only.split(",")}
        entries = [entry for entry in entries if entry.id in wanted]
    if args.area:
        entries = [entry for entry in entries if entry.area == args.area]
    outcomes = asyncio.run(run(entries))
    print(report(outcomes, show=args.show))
    sys.exit(1 if any(outcome.problems for outcome in outcomes) else 0)


if __name__ == "__main__":
    main()
