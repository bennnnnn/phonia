"""The system prompt as ordered sections, and the contracts placed beside the user turn.

Each ``PromptSection`` says when it applies to a ``PromptTurn`` and what text it adds.
The prompt is ordered most stable first, so a provider can reuse an earlier turn's
prefix (prompt caching), the chat's history included. ``STABLE_SECTIONS`` is the first
system message, the same text on every turn for this user: who Recall is, the tone and
unclear-message rules, their own instructions and language. ``TURN_SECTIONS`` is the
second: the rules this kind of turn needs (length, style, lookups), the profile and
the chat's summary; consecutive turns of one kind send it unchanged. The history comes
next. ``CONTEXT_SECTIONS`` is what changes on every turn (the clock, what memory, files
and the schedule returned for this message, and the notes that hang on it): it goes in
a system message after the history, so it never breaks the prefix before it. A section
whose text can change from one turn to the next never goes before the history. Each is
every applying section in table order, a blank line between parts. ``NEARBY_CONTRACTS``
go in one system message just before the user turn, after the context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.models.orm import User
from app.modules.account import profile as profile_service
from app.modules.chat import response_tone as response_tone_service
from app.modules.chat.clarify_turn import clarify_reply_hint
from app.modules.chat.continuation_subject import exchange_pairs, is_resume_request
from app.modules.chat.json_output import JSON_OUTPUT_HINT, is_json_request
from app.modules.chat.message_notes import message_notes
from app.modules.chat.prompt_constants import (
    ADVICE_PERSONALIZE_HINT,
    BREVITY_REQUEST_HINT,
    CAREER_PERSONALIZE_HINT,
    CODE_INK_REMINDER,
    CONTINUE_HINT,
    CORRECTION_HINT,
    EXAMPLE_PERSONALIZE_HINT,
    FACT_GROUNDING_HINT,
    LIGHTWEIGHT_REPLY_HINT,
    MATH_FENCE_SAFETY_HINT,
    PERSONAL_DISCLOSURE_HINT,
    PROFILE_FACT_HINT,
    SETTINGS_ASK_REMINDER,
    SETTINGS_IN_APP_HINT,
    SHORT_RESPONSE_FORMAT_HINT,
    STYLE_HINTS,
    TONE_FORMAT_GUARD,
    UNCLEAR_MESSAGE_HINT,
    WEB_SEARCH_OFF_HINT,
    is_bare_writing_line,
    learning_plan_daily_contract,
    programming_lesson_contract,
    repeated_greeting_hint,
    writing_format_hint,
)
from app.modules.chat.prompt_constants.multi_part import multi_part_contract
from app.modules.chat.prompt_constants.reactions import clock_is_relevant
from app.modules.chat.prompt_context_hints import integration_hints, lookup_hints, slim_geo_hints
from app.modules.chat.prompt_format import (
    PromptRule,
    _layout_format_hint,
    _style_format_hints,
    code_question_layout,
)
from app.modules.chat.prompt_memory import memory_notes, memory_status_note
from app.modules.chat.prompt_profile import (
    custom_instructions_block,
    format_user_name_only_block,
    format_user_profile_block,
    should_include_profile_email,
)
from app.modules.chat.prompt_subjects import SUBJECT_HINTS
from app.modules.turn_reading.capabilities import is_capabilities_question, names_a_setting
from app.modules.turn_reading.conversation import greeting_run, is_correction, is_social_opener
from app.modules.turn_reading.length import is_brevity_request, reply_length
from app.modules.turn_reading.lesson_flow import (
    active_lesson_step,
    lesson_after_gap,
    outline_awaits_pick,
)
from app.modules.turn_reading.personal import (
    is_career_personal_question,
    is_personal_disclosure_turn,
)
from app.modules.turn_reading.plan import TurnPlan
from app.modules.turn_reading.profile_ask import (
    is_profile_fact_question,
    is_profile_recall_pushback,
)
from app.modules.turn_reading.routing import is_short_confirmation
from app.modules.turn_reading.teaching import (
    is_learning_plan_request,
    is_standing_preference,
)
from app.modules.turn_reading.turn import teaching_of
from app.services import locale as locale_service
from app.services import time_context as time_context_service
from app.services.day_planning import is_day_planning_question
from app.services.prompt_safety import wrap_saved_memory, wrap_untrusted
from app.services.subjects.registry import SubjectName


@dataclass(frozen=True)
class PromptTurn:
    """What one turn's system prompt is built from."""

    user: User
    settings: Settings
    query_text: str | None
    local_tz: str
    lightweight: bool
    # Name-only profile and no integration context: casual or not about the user.
    slim: bool
    # Memory or earlier chats may answer this turn (slim turns state them on their own).
    recall_memory: bool
    advice_memory: bool
    minimal_personal_context: bool
    prompt_location: str | None
    summary: str | None
    memory_block: str
    attachment_rag_block: str
    todos_section: str | None
    chat_history_rag_block: str
    # The completed exchange before this turn (``PromptWindow.exchange``).
    exchange: list[Any]
    followup: SubjectName | None
    # The separate requests the message holds (``turn_prep.intents``), when more than one.
    plan: TurnPlan | None = None
    # How the memory read went ("ok", "partial", "unavailable"); see prompt_memory.
    memory_status: str = "ok"
    # Saving to memory is paused (spend cap) on a "remember …" turn.
    memory_paused: bool = False
    # "What did we decide last time": an earlier chat may answer this turn.
    recalls_shared_past: bool = False

    @property
    def query(self) -> str:
        return self.query_text or ""

    @property
    def length_hint(self) -> str:
        # No account-wide length: each message says how long it wants ("briefly",
        # "in detail").
        if self.lightweight:
            return STYLE_HINTS["short"]
        return STYLE_HINTS["detailed" if reply_length(self.query) == "detailed" else "balanced"]

    @property
    def multi(self) -> bool:
        return self.plan is not None and self.plan.multi


PromptSection = PromptRule[PromptTurn]


def _always(_turn: PromptTurn) -> bool:
    return True


def _present(text: str | None) -> list[str]:
    return [text] if text else []


def _profile(turn: PromptTurn) -> list[str]:
    if turn.slim:
        return [format_user_name_only_block(turn.user)]
    return [
        format_user_profile_block(
            turn.user,
            location_override=turn.prompt_location,
            include_email=should_include_profile_email(turn.query_text),
        )
    ]


def _style_hints(turn: PromptTurn) -> list[str]:
    query = turn.query
    lesson = active_lesson_step(turn.exchange)
    outline_pick = not lesson and outline_awaits_pick(turn.exchange)
    after_gap = bool(lesson) and lesson_after_gap(turn.exchange)
    # Greetings ("good morning!", "how are you?") and pasted fragments are compact.
    # "ok" / "next" after a lesson asks for the next lesson, not a casual reply.
    compact = not (lesson or outline_pick) and bool(
        query
        and (is_bare_writing_line(query) or is_short_confirmation(query) or is_social_opener(query))
    )
    return _style_format_hints(
        query_text=turn.query_text,
        is_day_plan=bool(query and is_day_planning_question(query)),
        minimal_personal_context=turn.minimal_personal_context,
        compact=compact,
        image_generation_enabled=turn.settings.image_generation_enabled,
        image_search_enabled=turn.settings.image_search_enabled,
        lesson=lesson,
        outline_pick=outline_pick,
        lesson_after_gap=after_gap,
        prior_messages=exchange_pairs(turn.exchange),
        multi=turn.multi,
    )


def _integrations(turn: PromptTurn) -> list[str]:
    return integration_hints(
        settings=turn.settings,
        query_text=turn.query_text,
        local_tz=turn.local_tz,
        user_locale=turn.user.locale,
        location_for_context=turn.prompt_location or profile_service.user_location_label(turn.user),
        prompt_location=turn.prompt_location,
        memory_block=turn.memory_block,
        attachment_rag_block=turn.attachment_rag_block,
        todos_section=turn.todos_section,
        chat_history_rag_block=turn.chat_history_rag_block,
    )


def _slim_memory(turn: PromptTurn) -> list[str]:
    parts = []
    if turn.memory_block:
        parts.append(wrap_saved_memory(turn.memory_block))
    return [*parts, *_present(turn.chat_history_rag_block)]


def _gives_advice(turn: PromptTurn) -> bool:
    return (
        turn.slim
        and turn.recall_memory
        and turn.advice_memory
        and not (turn.query and is_capabilities_question(turn.query))
    )


def _replied(turn: PromptTurn) -> bool:
    return any(message.role == "assistant" for message in turn.exchange)


def _resumes(turn: PromptTurn) -> bool:
    """After a reply, "continue" resumes it; in a lesson it asks for the next lesson."""
    if not is_resume_request(turn.query_text) or not _replied(turn):
        return False
    return not (active_lesson_step(turn.exchange) or outline_awaits_pick(turn.exchange))


def _card_reply(turn: PromptTurn) -> str | None:
    return clarify_reply_hint(turn.query_text, exchange_pairs(turn.exchange))


def _after_card(turn: PromptTurn) -> bool:
    return _card_reply(turn) is not None


def _advice(turn: PromptTurn) -> list[str]:
    query = turn.query
    if query and (is_profile_fact_question(query) or is_profile_recall_pushback(query)):
        # A failed memory read must not become "I don't have that yet" (memory_notes).
        return [] if memory_status_note(turn) else [PROFILE_FACT_HINT]
    if query and teaching_of(query):
        return [EXAMPLE_PERSONALIZE_HINT]
    if query and is_career_personal_question(query):
        return [CAREER_PERSONALIZE_HINT]
    return [ADVICE_PERSONALIZE_HINT]


# The same text on every turn for this user: the gateway marks it for the models that
# cache only a marked prefix. A section goes here only when its text never depends on
# the turn (its kind, its words, the clock or what was loaded for it).
STABLE_SECTIONS: tuple[PromptSection, ...] = (
    PromptSection(
        _always, lambda _t: ["You are Recall, a helpful personal AI assistant."], name="identity"
    ),
    PromptSection(
        _always,
        lambda t: [
            response_tone_service.tone_hint(t.user.response_tone),
            response_tone_service.emoji_hint(t.user.emoji_use),
            TONE_FORMAT_GUARD,
        ],
        name="tone",
    ),
    # "Bo" or "gd" may be a typo, another language or a half-typed message: the
    # model, which sees the conversation, decides; no word list or length gate.
    PromptSection(
        _always, lambda _t: [UNCLEAR_MESSAGE_HINT, SETTINGS_IN_APP_HINT], name="unclear_message"
    ),
    PromptSection(
        _always, lambda t: _present(custom_instructions_block(t.user)), name="custom_instructions"
    ),
    PromptSection(
        _always, lambda t: _present(locale_service.locale_system_hint(t.user.locale)), name="locale"
    ),
)


def _social_hint(turn: PromptTurn) -> str:
    """A greeting after a greeting is noticed, not answered as the first one."""
    prior = exchange_pairs(turn.exchange)
    run = greeting_run(turn.query, prior)
    if run < 2:
        return LIGHTWEIGHT_REPLY_HINT
    last_reply = next((content for role, content in reversed(prior) if role == "assistant"), None)
    return repeated_greeting_hint(run, last_reply)


# What the kind of turn needs, steadiest first so consecutive turns share a long
# prefix: the length and style the message asks for, the profile (name only on a slim
# turn, the email on a draft, the device location on a nearby ask), then the chat's
# summary (rewritten every few turns of a long chat). Nothing here may change from one
# turn of a kind to the next: the history after it is cached only behind it.
TURN_SECTIONS: tuple[PromptSection, ...] = (
    PromptSection(_always, lambda t: [t.length_hint], name="length"),
    # Lightweight/chit-chat turns skipped the math guardrails entirely,
    # so incidental `$...$` rendered as raw ```latex. A two-line fence
    # safety hint is enough — not the full math pack.
    PromptSection(
        lambda t: t.lightweight,
        lambda t: [_social_hint(t), SHORT_RESPONSE_FORMAT_HINT, MATH_FENCE_SAFETY_HINT],
        name="lightweight_social",
    ),
    PromptSection(lambda t: not t.lightweight, _style_hints, name="style_hints"),
    # A fact that may have changed is looked up or offered, never guessed.
    PromptSection(
        lambda t: not t.lightweight, lambda _t: [FACT_GROUNDING_HINT], name="fact_grounding"
    ),
    PromptSection(
        # The user's own choice, not a server without search: only then point to Settings.
        lambda t: not t.lightweight and t.user.web_search_enabled is False,
        lambda _t: [WEB_SEARCH_OFF_HINT],
        name="web_search_off",
    ),
    PromptSection(lambda t: not t.slim, lambda t: lookup_hints(t.settings), name="lookup_hints"),
    PromptSection(_always, _profile, name="profile"),
    # M8: inject the rolling summary even on the slim path. A slim long thread
    # (lightweight / not rich_context) still drops everything older than the
    # recent window from the prompt — without the summary the model loses all
    # context from earlier in the conversation. The summary is already
    # computed and is just a string, so including it is free.
    PromptSection(
        lambda t: bool(t.summary),
        lambda t: [
            wrap_untrusted("conversation summary", f"Summary of earlier conversation:\n{t.summary}")
        ],
        name="summary",
    ),
)


# What changes on every turn, after the history: the clock (to the second), what
# memory, files and the schedule returned for this message, and the notes and
# follow-up policies that hang on it. Before the history, any of it would leave the
# whole history uncached.
CONTEXT_SECTIONS: tuple[PromptSection, ...] = (
    # Not on a greeting, an ack or a reaction unless it names a time (reactions.py).
    PromptSection(
        lambda t: clock_is_relevant(t.lightweight, t.query_text),
        lambda t: [
            time_context_service.format_now_awareness(t.local_tz, t.user.locale, t.query_text)
        ],
        name="clock",
    ),
    PromptSection(lambda t: not t.slim, _integrations, name="integrations"),
    # "Coffee near me" is a slim turn, yet it needs the place and the places layout.
    PromptSection(
        lambda t: t.slim,
        lambda t: slim_geo_hints(t.settings, t.query_text, t.prompt_location),
        name="slim_geo",
    ),
    PromptSection(lambda t: t.slim and t.recall_memory, _slim_memory, name="slim_memory"),
    PromptSection(_gives_advice, _advice, name="advice"),
    PromptSection(_always, memory_notes, name="memory_notes"),
    PromptSection(
        _always,
        lambda t: message_notes(t.query, t.exchange, t.user, t.memory_block),
        name="message_notes",
    ),
    PromptSection(
        lambda t: t.followup == "math",
        lambda _t: list(SUBJECT_HINTS["math"].followup),
        name="math_followup",
    ),
    PromptSection(
        lambda t: t.followup == "chemistry",
        lambda _t: list(SUBJECT_HINTS["chemistry"].followup),
        name="chemistry_followup",
    ),
    PromptSection(
        lambda t: t.followup == "physics",
        lambda _t: list(SUBJECT_HINTS["physics"].followup),
        name="physics_followup",
    ),
    # Keep the acknowledgement contract closest to the user turn. Memory and
    # integration context is appended after the style pack and can otherwise
    # tempt the model into an unsolicited plan even though no task was asked.
    PromptSection(
        lambda t: (
            bool(t.query)
            and is_personal_disclosure_turn(t.query)
            and not is_standing_preference(t.query)
        ),
        lambda _t: [PERSONAL_DISCLOSURE_HINT],
        name="personal_disclosure",
    ),
)


# Repeat only the machine-checkable turn contract immediately before the
# current user message. Smaller low-latency models follow nearby system
# constraints more reliably than a clause inside the large base prompt.
def part_shape_hints(text: str) -> list[str]:
    """One request's own length or layout: "in one sentence" binds only its request."""
    if is_brevity_request(text):
        return [BREVITY_REQUEST_HINT]
    writing = writing_format_hint(text)
    if writing:
        return [writing]
    hints = _present(_layout_format_hint(text))
    if is_learning_plan_request(text):
        hints.extend(_present(learning_plan_daily_contract(text)))
    elif teaching_of(text):
        hints.extend(_present(programming_lesson_contract(text)))
    return hints


def _multi_part(turn: PromptTurn) -> list[str]:
    """Every request answered, each in its own section and its own shape."""
    plan = turn.plan
    if plan is None:
        return []
    shapes = [part_shape_hints(part.text) for part in plan.parts]
    return [multi_part_contract(plan, shapes)]


# A message with several requests gets the lesson contracts per request, in its own.
NEARBY_CONTRACTS: tuple[PromptSection, ...] = (
    PromptSection(
        lambda t: bool(t.query) and not t.multi and is_learning_plan_request(t.query),
        lambda t: _present(learning_plan_daily_contract(t.query)),
        name="learning_plan_contract",
    ),
    PromptSection(
        lambda t: bool(t.query) and not t.multi and teaching_of(t.query),
        lambda t: _present(programming_lesson_contract(t.query)),
        name="programming_lesson_contract",
    ),
    # Pasted code to explain or fix: the `$...$` math rule must not reach its values.
    PromptSection(
        lambda t: not t.lightweight and bool(code_question_layout(t.query_text)),
        lambda _t: [CODE_INK_REMINDER],
        name="code_ink",
    ),
    # The message after a clarify card: the picks, a skip, or something typed instead.
    PromptSection(_after_card, lambda t: _present(_card_reply(t)), name="card_reply"),
    # "continue" resumes the last reply; it does not start over or recap.
    PromptSection(_resumes, lambda _t: [CONTINUE_HINT], name="continue"),
    # "no, I said I'm vegetarian": the correction wins over what the last reply assumed.
    PromptSection(
        lambda t: bool(t.query) and _replied(t) and is_correction(t.query),
        lambda _t: [CORRECTION_HINT],
        name="correction",
    ),
    # "Use the pro model by default": no card; the reply says where, not "done".
    PromptSection(
        lambda t: names_a_setting(t.query_text),
        lambda _t: [SETTINGS_ASK_REMINDER],
        name="settings_ask",
    ),
    # Asked-for JSON is checked at finalize (``json_output``); say the shape up front.
    PromptSection(
        lambda t: is_json_request(t.query_text), lambda _t: [JSON_OUTPUT_HINT], name="json_output"
    ),
    # Last, closest to the user turn: what the reply must hold.
    PromptSection(lambda t: t.multi, _multi_part, name="multi_part"),
)
