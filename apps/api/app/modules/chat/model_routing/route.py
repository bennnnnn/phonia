"""Automatic model routing.

When a request uses the ``auto`` alias (or a user whose default model is
``auto``), pick a concrete model per message: cheap/fast for simple turns,
the stronger model for genuinely hard ones. Heuristic only — no extra LLM call.

Routing always respects the caller's allowed model pool (plan + enabled toggles).
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import Settings
from app.models import model_catalog
from app.modules.billing.plan import (
    pick_cheapest_from_pool,
    pick_fast_from_pool,
    pick_preferred_tier,
    pick_smart_from_pool,
)
from app.modules.chat.model_routing.signals import SMART_TRIGGERS, needs_strong_model
from app.modules.chat.turn_trace import note_route

_FOLLOWUP_MAX_CHARS = 120
# Linear phrase scan — same style as prompt_constants.routing `_OFFER_PHRASES`.
# Do not add bare "fix" to `SMART_TRIGGERS`; that would pin every "fix dinner"
# ask onto the strong model.
_FOLLOWUP_CUES = (
    "now fix",
    "fix it",
    "try again",
    "also",
    "instead",
    "the tests",
    "the error",
    "keep going",
    "next step",
    "make it",
    "change it",
    "do that",
)
_FOLLOWUP_LEAD_VERBS = frozenset(
    {
        "add",
        "fix",
        "retry",
        "patch",
        "update",
        "continue",
        "check",
        "verify",
        "handle",
        "review",
        "test",
    }
)
# Leading verb alone is not enough ("fix dinner", "add milk"). The rest of
# the line must refer to the prior task.
_FOLLOWUP_OBJECT_TOKENS = frozenset(
    {
        "it",
        "that",
        "this",
        "them",
        "these",
        "those",
        "tests",
        "test",
        "error",
        "errors",
        "bug",
        "bugs",
        "traceback",
        "types",
        "type",
        "handling",
        "handler",
        "patch",
        "retry",
        "retries",
        "function",
        "functions",
        "code",
        "timeout",
        "edge",
        "cases",
    }
)

_LONG_MESSAGE_CHARS = 800
# Any fence opener counts as code, with or without a language tag: an allowlist of
# languages left a bare fence, or bash, Kotlin or HTML, on the cheap model.
#
# The leading whitespace is ``[ \t]*``, not ``\s*``: ``\s`` overlaps the ``\n`` that
# ``(?:^|\n)`` matches, and a message of thousands of blank lines with no closing fence
# went quadratic (CodeQL polynomial regex). ``[ \t]*`` cannot eat a newline, so each
# line is scanned once.
_CODE_FENCE = re.compile(r"(?:^|\n)[ \t]*```")


def last_user_turn(messages: list[Any] | None) -> tuple[str | None, str | None]:
    """Last user line and the model stored on that row (oldest-first window).

    The current turn is not persisted yet. ``model`` is the alias resolved for
    that prior user turn — used so a chain of short follow-ups can keep Pro
    without re-scoring ``add tests`` in isolation.
    """
    if not messages:
        return None, None
    for msg in reversed(messages):
        if getattr(msg, "role", None) != "user":
            continue
        text = getattr(msg, "content", None)
        if not isinstance(text, str) or not text.strip():
            continue
        raw_model = getattr(msg, "model", None)
        model = raw_model.strip() if isinstance(raw_model, str) and raw_model.strip() else None
        return text, model
    return None, None


def _strip_followup_token(token: str) -> str:
    while token and token[0] in ".,!?;:'\"":
        token = token[1:]
    while token and token[-1] in ".,!?;:'\"":
        token = token[:-1]
    return token


def _alias_is_smart_tier(alias: str | None) -> bool:
    if not alias or alias not in model_catalog.known_ids():
        return False
    return model_catalog.get(alias).tier in {"smart", "max"}


def _prior_was_smart(prior_user: str, prior_model: str | None) -> bool:
    if _alias_is_smart_tier(_route_current_line(prior_user)):
        return True
    return _alias_is_smart_tier(prior_model)


def _leading_followup_verb(lowered: str) -> bool:
    if not lowered or " " not in lowered:
        return False
    first, rest = lowered.split(" ", 1)
    while first and first[-1] in ".,!?;:":
        first = first[:-1]
    if first not in _FOLLOWUP_LEAD_VERBS:
        return False
    for raw in rest.split():
        if _strip_followup_token(raw) in _FOLLOWUP_OBJECT_TOKENS:
            return True
    return False


def _looks_like_smart_continuation(content: str) -> bool:
    """True when this line continues the prior hard turn, not a new topic."""
    from app.modules.chat.continuation_subject import is_pure_continuation
    from app.modules.turn_reading.personal import is_personal_advice_question
    from app.modules.turn_reading.routing import is_lightweight_chat_turn, is_short_confirmation
    from app.modules.turn_reading.writing_kind import is_writing_deliverable_request
    from app.services.day_planning import is_day_planning_question
    from app.services.text_normalize import collapse_ws

    if is_personal_advice_question(content):
        return False
    if is_day_planning_question(content):
        return False
    if is_writing_deliverable_request(content):
        return False
    cleaned = collapse_ws(content)
    if len(cleaned) > _FOLLOWUP_MAX_CHARS:
        return False
    lowered = cleaned.lower().rstrip(" .,!?:;")
    if is_pure_continuation(content):
        return True
    # These are lightweight as standalone chat, but after a hard answer they
    # explicitly ask for its reasoning. Keep them on the same strong lane.
    if lowered in {"how", "how so", "why", "why not", "show me how", "explain how"}:
        return True
    # A learner normally names the exact disputed step after the question
    # word ("why is x=-1 rejected?", "how did you factor that?"). Requiring
    # the whole message to equal bare ``why``/``how`` dropped these natural
    # follow-ups onto the lightweight lane.
    if lowered.startswith(("why ", "how ")):
        return True
    # yes / go / sure inherit; hi / thanks do not (those are lightweight acks).
    if is_short_confirmation(content):
        return True
    if is_lightweight_chat_turn(content):
        return False
    lowered = cleaned.lower()
    # Politeness should not change whether a task continuation inherits its tier.
    for prefix in ("please ", "can you ", "could you ", "would you "):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :]
    if any(cue in lowered for cue in _FOLLOWUP_CUES):
        return True
    return _leading_followup_verb(lowered)


def _should_inherit_smart(
    content: str,
    prior_user: str,
    prior_model: str | None = None,
) -> bool:
    """Inherit Pro when the last user turn was (or stayed) on the smart tier."""
    if not _prior_was_smart(prior_user, prior_model):
        return False
    return _looks_like_smart_continuation(content)


def _route_current_line(content: str, settings: Settings | None = None) -> str:
    """Score this message alone — no prior-turn inherit."""
    return _routed_line(content, settings)[0]


def _routed_line(content: str, settings: Settings | None = None) -> tuple[str, str]:
    """``_route_current_line``'s alias and why it was chosen (the turn's trace)."""
    text = content.lower()
    smart = model_catalog.auto_smart_alias()
    fast = model_catalog.auto_fast_alias()
    if len(content) >= _LONG_MESSAGE_CHARS:
        return smart, "long_message"
    if _CODE_FENCE.search(content):
        return smart, "code"
    # Tutoring is structured by a strict prompt contract and is latency-sensitive:
    # a learner should not wait on a silent reasoning model before every small
    # step. The fast lane (then Gemini Flash) followed the lesson contract in
    # live QA at a fraction of the TTFT, so keep this classifier shared with the
    # prompt layer and use the fast lane. Hard coding/math still reaches the
    # smart checks below when it is not an explicit tutor/roadmap request.
    from app.modules.turn_reading.teaching import is_learning_plan_request
    from app.modules.turn_reading.turn import teaching_of

    if is_learning_plan_request(content) or teaching_of(content):
        return fast, "teaching"
    # A request whose task is to *format* a small example as a Markdown table
    # is not a deep architecture/trade-off analysis. The column label
    # "Main tradeoff" previously tripped the generic smart cue and sent this
    # UI/layout stress case to R1, which could sit silent for tens of seconds.
    if "markdown table" in text and any(
        cue in text for cue in ("create ", "show ", "give me ", "make ")
    ):
        return fast, "table_layout"
    if any(trigger in text for trigger in SMART_TRIGGERS):
        return smart, "smart_trigger"
    from app.modules.turn_reading.writing_kind import is_writing_deliverable_request

    # A tweet or an email about a migration is writing, not the migration.
    if needs_strong_model(content) and not is_writing_deliverable_request(content):
        return smart, "strong_task"
    from app.services.subjects.dispatch import detect_subject

    # The lane follows the subject whose solver answers the line (code-health audit
    # DUP-05): a balanced equation or a molarity is chemistry's card, not the maths
    # lane's algebra, and a curve's maximum is maths' though it cues physics.
    chemistry_enabled = settings is None or settings.chemistry_enabled
    subject = detect_subject(content, chemistry_enabled=chemistry_enabled)
    from app.modules.turn_reading.school_question import needs_reasoned_choice

    # An exercise's option or verdict, reasoned before it is written (school_question);
    # a maths one keeps the maths lane below.
    if subject != "math" and needs_reasoned_choice(content):
        return smart, "reasoned_choice"
    from app.services.subjects.registry import subject_adapter

    tools_on = settings is None or settings.math_tools_enabled
    if subject == "chemistry":
        chemistry_fast = subject_adapter("chemistry").fast_lane(content, tools_on=tools_on)
        return (fast if chemistry_fast else smart), "chemistry"
    if subject != "math":
        physics_fast = subject_adapter("physics").fast_lane(content, tools_on=tools_on)
        if physics_fast is not None:
            return (fast if physics_fast else smart), "physics"
    # Math turns (equations, graphs, geometry, calculus, stats, …) go to the math-tuned
    # strong model: a fast model's steps disagreed with the verified answer.
    from app.modules.chat.model_routing.rate_problems import is_multi_step_rate_problem

    if is_multi_step_rate_problem(content):  # catch-up, meet, together: the maths lane won't think
        return smart, "rate_problem"
    if subject == "math" and not subject_adapter("math").fast_lane(content, tools_on=tools_on):
        return model_catalog.auto_math_alias(), "math"
    return fast, "math_verified" if subject == "math" else "everyday"


def route_chat_model(
    content: str,
    *,
    prior_user: str | None = None,
    prior_model: str | None = None,
    lesson_active: bool = False,
    settings: Settings | None = None,
) -> str:
    """Preferred chat alias for an auto-routed message (before pool filter).

    Lessons stay on the low-latency tier. "That's wrong" after an answer goes to
    the thinking tier; otherwise a short continuation of a smart turn inherits it.
    """
    return routed_chat_model(
        content,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=lesson_active,
        settings=settings,
    )[0]


def routed_chat_model(
    content: str,
    *,
    prior_user: str | None = None,
    prior_model: str | None = None,
    lesson_active: bool = False,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """``route_chat_model``'s alias and a short code saying why (the turn's trace)."""
    from app.modules.chat.model_routing.thinking import is_answer_dispute

    smart = model_catalog.auto_smart_alias()
    if lesson_active:
        return model_catalog.auto_fast_alias(), "lesson"
    if prior_user and is_answer_dispute(content):
        return smart, "dispute"
    preferred, reason = _routed_line(content, settings)
    if preferred == smart:
        return smart, reason
    if (
        prior_user
        and prior_user.strip()
        and _should_inherit_smart(content, prior_user, prior_model)
    ):
        math = model_catalog.auto_math_alias()
        if prior_model == math or _route_current_line(prior_user, settings) == math:
            return math, "inherit_math"
        return smart, "inherit_smart"
    return preferred, reason


def message_needs_thinking(
    content: str,
    *,
    prior_user: str | None = None,
    prior_model: str | None = None,
    lesson_active: bool = False,
    settings: Settings | None = None,
) -> bool:
    """True only when this job should spend a reasoning pass.

    The same split Auto uses for the strong lane, except the math lane:
    an equation still uses a strong model, and it does not think first.
    """
    return (
        route_chat_model(
            content,
            prior_user=prior_user,
            prior_model=prior_model,
            lesson_active=lesson_active,
            settings=settings,
        )
        == model_catalog.auto_smart_alias()
    )


_MODES = frozenset({"auto", "fast", "smart"})


def resolve_alias_in_pool(
    alias: str,
    content: str,
    pool: list[str],
    settings: Settings | None = None,
    *,
    prior_user: str | None = None,
    prior_model: str | None = None,
    lesson_active: bool = False,
    unhealthy: frozenset[str] = frozenset(),
) -> str:
    """Resolve a model mode or alias within an allowed pool.

    A concrete alias is the user's pick and passes through. A mode (auto, fast,
    smart) chooses among the pool's healthy models, and for a JSON ask among those
    with JSON mode (``_usable_pool``).
    """
    if not pool:
        note_route("no_pool")
        return model_catalog.auto_fast_alias()
    if alias not in _MODES:
        note_route("picked" if alias in pool else "picked_unavailable")
        return alias if alias in pool else pick_cheapest_from_pool(pool, settings)
    usable = _usable_pool(pool, unhealthy, content)
    if alias == "fast":
        note_route("mode_fast")
        return pick_fast_from_pool(usable)
    if alias == "smart":
        note_route("mode_smart")
        return pick_smart_from_pool(usable)
    preferred, reason = routed_chat_model(
        content,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=lesson_active,
        settings=settings,
    )
    note_route(f"auto.{reason}")
    return pick_preferred_tier(preferred, usable)


def _usable_pool(pool: list[str], unhealthy: frozenset[str], content: str) -> list[str]:
    """The pool without unhealthy models; for a JSON ask, only models with JSON mode.

    Each filter applies only while it leaves a model: a degraded model beats none.
    """
    from app.modules.chat.json_output import is_json_request

    usable = [model_id for model_id in pool if model_id not in unhealthy] or pool
    if not is_json_request(content):
        return usable
    known = model_catalog.known_ids()
    with_json = [m for m in usable if m in known and model_catalog.get(m).json_mode]
    return with_json or usable
