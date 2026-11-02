"""Route one battery prompt through the real turn path, offline, and say what happened.

The turn runs the way ``stream_entry`` runs it: the photo-lookup and image-generation
intercepts, the turn mode, the real prompt builder and pre-solvers, then the tool-loop
gate. Only IO is stubbed: the database, model health, the web and image
search providers, PubChem, and the model calls. The tool rounds are recorded instead of
called, so the route says whether a model would have been asked. Settings are
production's: the battery certifies what users get.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.config import Settings
from app.gateways.mcp import registry as tool_registry
from app.gateways.pubchem_gateway import PubChemCompound, PubChemResult
from app.gateways.web_search_gateway import WebSearchHit
from app.models.orm import Chat, User
from app.modules import web_search as web_search_service
from app.modules.billing import can_use
from app.modules.chat import prompt_constants as pc
from app.modules.chat import prompt_memory
from app.modules.chat.finalize_passes import enrich_final_content
from app.modules.chat.json_output import JSON_OUTPUT_HINT
from app.modules.chat.model_routing import choice as model_choice
from app.modules.chat.model_routing.route import last_user_turn
from app.modules.chat.prompt_constants.clarify import CLARIFY_PICKS_HINT, CLARIFY_UNANSWERED_HINT
from app.modules.chat.prompt_constants.coding import (
    CODE_DEBUG_HINT,
    CODE_EXPLAIN_HINT,
    CODE_RUN_HINT,
)
from app.modules.chat.prompt_constants.conversation import CONFIRMED_HINT
from app.modules.chat.prompt_constants.multi_part import MULTI_PART_MARKER
from app.modules.chat.prompt_constants.reply_missed import REPLY_MISSED_HINT
from app.modules.chat.prompt_constants.shared_numbers import SHARED_NUMBERS_HINT
from app.modules.chat.prompt_constants.worked import WORKED_BLOCK_CONTRACT
from app.modules.chat.prompt_constants.writing import (
    EMAIL_ASK_PURPOSE_HINT,
    EMAIL_DRAFT_HINT,
    NON_DRAFT_TURN_HINT,
    PERSONAL_RECORD_HINT,
    SOCIAL_DRAFT_HINT,
)
from app.modules.chat.prompt_context import _PromptContextBlocks
from app.modules.chat.stream_paths import run_tool_loop_path
from app.modules.chat.tool_loop.selection import _search_before_the_model
from app.modules.chat.turn_deps import default_deps
from app.modules.chat.turn_intercepts import _chemistry_draws_it, reply_picture_prompt
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep.context import (
    build_stream_prompt_context,
    stream_context_from_bundle,
)
from app.modules.chat.turn_prep.mode import classify_turn_mode
from app.modules.chat.turn_prep.request import TurnRequest
from app.modules.chat.turn_trace import TurnTrace, begin_turn_trace
from app.modules.images.gen_intent import stem_subject_claims
from app.modules.images.intent import image_gen_request
from app.modules.images.lookup_intent import dated_lookup_query, extract_image_lookup_query
from app.modules.money.block import (
    MONEY_HEADER,
    MONEY_RATE_MISSING,
    MONEY_RATES_MISSING,
    MONEY_REPLY_RULES,
    MONEY_STANDING_HEADER,
    MONEY_WORKED_RULES,
)
from app.modules.physics.schemas.simulation import SIMULATION_SPEC_TYPES
from app.modules.turn_reading.lesson_flow import active_lesson_step
from app.modules.web_search.detection import needs_web_search
from app.services.mcp import setup_mcp_adapters
from app.services.solving import VerifiedPhysicsBlock
from app.services.subjects.dispatch import detect_subject
from app.services.workout import SELF_CHECK_PROMPT_RULE
from app.tests.behavior.cases import Case, Expect
from app.tests.fakes import fake_session

# The user's emoji setting; the battery's user has the default, a few.
EMOJI_RULE = "Emoji: a few, to help the reader scan."

# Name → text that marks the hint in the system prompt.
HINTS: dict[str, str] = {
    "teaching": pc.TEACHING_HINT,
    "walkthrough": pc.WALKTHROUGH_HINT,
    "learning_plan": pc.LEARNING_PLAN_HINT,
    "comparison": pc.COMPARISON_FORMAT_HINT,
    "howto": pc.HOWTO_FORMAT_HINT,
    "checklist": pc.CHECKLIST_FORMAT_HINT,
    "steps": pc.STEPS_FORMAT_HINT,
    "chart": pc.CHART_FORMAT_HINT,
    "mermaid": pc.MERMAID_FORMAT_HINT,
    "diagram": pc.DIAGRAM_KIND_HINT,
    "quiz": pc.QUIZ_FORMAT_HINT,
    "clarify": pc.CLARIFY_CARD_HINT,
    "clarify_picks": CLARIFY_PICKS_HINT,
    "clarify_unanswered": CLARIFY_UNANSWERED_HINT,
    # "Yes" to the last reply's request to confirm something: it is confirmed.
    "confirmed": CONFIRMED_HINT,
    # Any money turn; its reply rules; asking for the rate; no checked average for "rates now".
    "money": MONEY_HEADER,
    "money_reply": MONEY_REPLY_RULES,
    # A lesson's money problem, every number its own: laid out Given / Formula / Answer.
    "money_worked": MONEY_WORKED_RULES,
    # A turn about the chat's earlier loan: its figures, worked by the app.
    "money_standing": MONEY_STANDING_HEADER,
    "money_ask_rate": MONEY_RATE_MISSING,
    "money_rates": MONEY_RATES_MISSING,
    "email": EMAIL_DRAFT_HINT,
    "ask_purpose": EMAIL_ASK_PURPOSE_HINT,
    "social": SOCIAL_DRAFT_HINT,
    # A cover letter, résumé or bio: only facts the user gave or memory holds.
    "personal_record": PERSONAL_RECORD_HINT,
    # "Do not create an email, message ... fence": the turn is no draft.
    "no_draft": NON_DRAFT_TURN_HINT,
    # The draft asked for earlier, written or changed on this turn.
    "draft_revision": "This turn changes the draft you wrote earlier",
    "draft_now": "and this turn says what it should say or how to change it",
    "brevity": pc.BREVITY_REQUEST_HINT,
    "capabilities": pc.CAPABILITIES_FORMAT_HINT,
    "lightweight": pc.LIGHTWEIGHT_REPLY_HINT,
    "greeting_again": pc.REPEATED_GREETING_HINT,
    "web_search": web_search_service.WEB_SEARCH_HINT,
    "photo": pc.PHOTO_LOOKUP_HINT,
    "local_places": web_search_service.LOCAL_PLACES_FORMAT_HINT,
    "answer_photo": pc.ANSWER_PHOTO_HINT,
    "where_is_photo": pc.WHERE_IS_PHOTO_HINT,
    # The subject is the user's own words; its fixed part marks the hint.
    "subject_photo": "If that is something people would want to see",
    "emoji_rule": EMOJI_RULE,
    "code_explain": CODE_EXPLAIN_HINT,
    "code_debug": CODE_DEBUG_HINT,
    "code_run": CODE_RUN_HINT,
    "code_ink": pc.CODE_INK_REMINDER,
    "standing_preference": pc.STANDING_PREFERENCE_HINT,
    "personal_disclosure": pc.PERSONAL_DISCLOSURE_HINT,
    # A list of numbers that asks nothing: its highest and lowest, and no greeting.
    "shared_numbers": SHARED_NUMBERS_HINT,
    # "What?" right after a reply: say it again more simply.
    "reply_missed": REPLY_MISSED_HINT,
    # "The user is asking for a personal recommendation": tastes shape the pick.
    "advice": pc.ADVICE_PERSONALIZE_HINT,
    # A STEM reply the model works out itself checks its own answer first.
    "self_check": SELF_CHECK_PROMPT_RULE,
    # A calculation nothing verified: its parts in a ```worked block the server lays out.
    "worked": WORKED_BLOCK_CONTRACT,
    # The general layout contract, and the compact one a greeting or fragment gets.
    "format_contract": pc.FORMAT_CONTRACT,
    "compact": pc.COMPACT_RESPONSE_FORMAT_HINT,
    # The length line: fit to the question, or the depth the message asked for.
    "fit_length": pc.STYLE_HINTS["balanced"],
    "detail": pc.STYLE_HINTS["detailed"],
    "mixed_length": pc.MIXED_LENGTH_HINT,
    "continue": pc.CONTINUE_HINT,
    "correction": pc.CORRECTION_HINT,
    "json_output": JSON_OUTPUT_HINT,
    # Two or more separate requests: every one answered, each in its own section.
    "multi_intent": MULTI_PART_MARKER,
    # "In one sentence" binds only the request that said it.
    "part1_brevity": f"For request 1 only: {pc.BREVITY_REQUEST_HINT}",
    # Memory is off, or has no record of the earlier chat the user recalls.
    "memory_off": prompt_memory.MEMORY_OFF_HINT,
    "no_past_record": prompt_memory.NO_PAST_RECORD_HINT,
}

USER_NAME = "Bini"
USER_TIMEZONE = "Africa/Nairobi"


@dataclass
class Route:
    """What the turn did. Mirrors ``Expect``."""

    photo: str
    image_gen: bool
    search: str
    subject: str
    solved: bool
    instant: str
    lightweight: bool
    # The model Auto picks for the case's plan.
    model: str = ""
    hints: set[str] = field(default_factory=set)
    # The ``programming_lesson`` contract is turn-specific text, not a constant.
    system_prompt: str = ""
    # What an instant (no-model) reply said, for the sweep to read.
    instant_text: str = ""
    # The verified result handed to the model when it writes the reply itself.
    verified_answer: str = ""
    verified_text: str = ""
    # A multi-part message's picture and settings card (the server's part of its reply).
    picture: bool = False
    settings_card: str = ""
    # The last reply asked with a clarify card: this reply may not ask again.
    after_card: bool = False
    # Saved memory was read for this turn, and with which scope; earlier chats searched.
    memory: bool = False
    memory_scope: str = ""
    history_rag: bool = False
    # The scenes a verified block appends under a model-written reply, as fences.
    server_pictures: str = ""
    # What the turn decided, as production records it (``turn_trace``): the trace keeps
    # collecting while the caller runs the reply's finalize step. ``decisions.py`` reads
    # both to diff a change's decisions against main's.
    trace: TurnTrace | None = None
    context: Any = None

    def summary(self) -> str:
        parts = [f"search={self.search}"]
        if self.photo:
            parts.append(f"photo={self.photo!r}")
        if self.image_gen:
            parts.append("image_gen")
        if self.picture:
            parts.append("picture")
        if self.settings_card:
            parts.append("settings_card")
        if self.subject:
            parts.append(f"subject={self.subject}{'+solved' if self.solved else ''}")
        if self.instant:
            parts.append(f"instant={self.instant}")
        if self.lightweight:
            parts.append("lightweight")
        if self.model:
            parts.append(f"model={self.model}")
        if self.memory:
            parts.append(f"memory={self.memory_scope}")
        if self.history_rag:
            parts.append("history_rag")
        if self.hints:
            parts.append("hints=" + ",".join(sorted(self.hints)))
        return " ".join(parts)


@contextmanager
def _production_tools(settings: Settings) -> Iterator[None]:
    """The model's tools as production registers them at startup, then the registry as it was."""
    before = tool_registry.list_adapters()
    setup_mcp_adapters(settings)
    try:
        yield
    finally:
        tool_registry.clear()
        for adapter in before:
            tool_registry.register(adapter)


def battery_settings() -> Settings:
    """Every feature on, no provider keys: nothing leaves the process."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        mock_llm_enabled=True,
        openrouter_api_key="",
        openai_api_key="",
        tavily_api_key="",
        web_search_enabled=True,
        web_search_fallback_enabled=False,
        image_search_enabled=True,
        image_generation_enabled=True,
        math_tools_enabled=True,
        # Coverage, not speed: a busy CI machine must not turn a 0.7s solve
        # into an unanswered turn at the production 5s limit.
        stem_solve_timeout_seconds=30.0,
        # The same for the turn's one reading: a slow read is a declined question, and the
        # STEM snapshot holds every answered question by name.
        subject_read_timeout_seconds=30.0,
        chemistry_enabled=True,
        mcp_tool_loop_enabled=True,
        attachments_enabled=False,
        attachment_rag_enabled=False,
        chat_history_rag_enabled=False,
        semantic_memory_enabled=False,
    )


class _Session:
    async def __aenter__(self) -> AsyncMock:
        return fake_session()

    async def __aexit__(self, *_args: object) -> None:
        return None


# The one compound a battery prompt names; every other lookup is "not found".
_PUBCHEM = {
    "caffeine": PubChemCompound(
        cid=2519,
        name="caffeine",
        smiles="CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
        molecular_formula="C8H10N4O2",
        molecular_weight=194.19,
    ),
}


async def _pubchem_lookup(name: str, *_args: Any, **_kwargs: Any) -> PubChemResult:
    compound = _PUBCHEM.get(" ".join(name.split()).lower())
    return PubChemResult(compound=compound) if compound else PubChemResult(error="not found")


def _rows(case: Case) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id=uuid4(), role=role, content=text, model="free-chat")
        for role, text in case.history
    ]


def is_picture_only(block: object) -> bool:
    """A physics block that carries a picture and no verified result."""
    return (
        isinstance(block, VerifiedPhysicsBlock)
        and block.physics_intent is None
        and block.symbolic_request is None
        and not (block.canonical_answer or block.display_answer)
    )


def _instant_kind(reply: str | None, *, solved: bool) -> str:
    if not reply:
        return ""
    if reply.lstrip().startswith("```clock"):
        return "clock"
    if reply == web_search_service.format_location_not_set_answer():
        return "location"
    if solved:
        return "solver"
    return "text"


def _hints_in(system: str, case: Case) -> set[str]:
    found = {name for name, text in HINTS.items() if text and text in system}
    contract = pc.programming_lesson_contract(case.prompt)
    if contract and contract in system:
        found.add("programming_lesson")
    return found


async def route_case(case: Case, settings: Settings | None = None) -> Route:
    settings = settings or battery_settings()
    trace = begin_turn_trace("new")
    user = User(
        id=uuid4(),
        name=USER_NAME,
        email="bini@example.com",
        plan="pro" if case.pro else "free",
        response_tone="casual",
        emoji_use="some",
        locale=case.locale,
        timezone=USER_TIMEZONE,
        memory_enabled=case.memory_enabled,
        location=case.location,
        location_enabled=case.location is not None,
    )
    chat = Chat(id=uuid4(), user_id=user.id, title=None)
    rows = _rows(case)
    text = case.prompt
    prior_user, prior_model = last_user_turn(rows)
    model = model_choice.resolve_user_model(
        user,
        text,
        settings,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=active_lesson_step(rows) is not None,
    )

    # "can u show me both" after a shape answer: the intercept lets chemistry draw the
    # molecules before a photo lookup or image generation is asked.
    drawn = await _chemistry_draws_it(settings, text, rows)
    found = extract_image_lookup_query(text) if settings.image_search_enabled else None
    photo = dated_lookup_query(found, datetime.now(UTC).year) if found and not drawn else ""
    image_gen = bool(
        not photo
        and not drawn
        and settings.image_generation_enabled
        and can_use(user, "image_generation", settings)
        # Read with the thread, as the turn's intercept reads it ("Image" after "Dog").
        and image_gen_request(text, rows, revisions=bool(rows)) is not None
        and not stem_subject_claims(text, chemistry_enabled=settings.chemistry_enabled)
    )

    searched: list[Any] = []

    async def run_search(*args: Any, **_kwargs: Any) -> tuple[list[WebSearchHit], list[str]]:
        searched.append(args)
        hit = WebSearchHit(title="Result", url="https://example.com", snippet="A result.")
        return [hit], [text]

    tool_rounds = AsyncMock(side_effect=lambda **kw: (kw["messages"], None, None, []))
    # What the prompt builder asked to load: the memory scope, and earlier chats.
    loaded: dict[str, Any] = {}

    async def context_blocks(*_args: Any, **kwargs: Any) -> _PromptContextBlocks:
        loaded.update(kwargs)
        return _PromptContextBlocks(
            memory_block="",
            todos_section=None,
            recent_all=list(rows),
            attachment_rag_block="",
            chat=chat,
        )

    with ExitStack() as stack:

        def stub(target: str, value: Any) -> None:
            stack.enter_context(patch(target, value))

        stub("app.modules.chat.turn_prep.instant.SessionLocal", lambda: _Session())
        stub("app.modules.chat.prompt_builder._load_context_blocks", context_blocks)
        stub(
            "app.modules.conversation.messages_repository.list_recent",
            AsyncMock(return_value=list(rows)),
        )
        stub("app.modules.memory.repository.list_for_user", AsyncMock(return_value=[]))
        stub("app.services.model_health.enrich_models_health", AsyncMock(return_value={}))
        stub("app.modules.billing.plan.chat_fallback_models", lambda *_a, **_k: [])
        stub("app.modules.web_search.search_cache.run_cached_search", run_search)
        stub("app.gateways.web_search_gateway.search_web", AsyncMock(return_value=[]))
        stub("app.gateways.pubchem_gateway.lookup_by_name", _pubchem_lookup)
        stub("app.gateways.pubchem_gateway.lookup_iupac_name", AsyncMock(return_value=None))
        stub("app.modules.chat.tool_loop.run_tool_rounds", tool_rounds)
        stub("app.services.quota.global_spend_exceeded", AsyncMock(return_value=False))
        stack.enter_context(_production_tools(settings))

        turn_mode = classify_turn_mode(list(rows), text)
        bundle = await build_stream_prompt_context(
            TurnRequest(
                user_id=user.id,
                chat_id=chat.id,
                content=text,
                model=model,
                client_timezone=USER_TIMEZONE,
                client_location=case.location,
                client_latitude=None,
                client_longitude=None,
                user=user,
                chat=chat,
                turn_mode=turn_mode,
                recent_messages=list(rows),
            ),
            settings,
            AsyncMock(),
        )
        ctx = stream_context_from_bundle(
            bundle,
            user_id=user.id,
            chat_id=chat.id,
            model=model,
            user_message_content=text,
            reserved_tokens=100,
            user=user,
            prior_count=len(rows),
        )
        prefetch_searched = bool(searched)
        await run_tool_loop_path(
            default_deps(), AsyncMock(), settings, ctx, usage={}, on_status=None, should_cancel=None
        )

    loop_call = tool_rounds.await_args
    loop_ran = loop_call is not None
    web_flag = loop_call.kwargs.get("web_search") if loop_call is not None else None
    verified_part = bool(loop_call and loop_call.kwargs.get("has_verified_math"))
    direct = loop_ran and _search_before_the_model(
        text, settings, user, web_search=web_flag, has_verified_math=verified_part
    )
    if prefetch_searched or direct or (loop_ran and needs_web_search(text)):
        search = "yes"
    elif loop_ran or ctx.reply_tools:
        # The tool loop's model, or the reply's own model call, may call web_search.
        search = "ask"
    else:
        search = "no"

    subject = detect_subject(text, chemistry_enabled=settings.chemistry_enabled) or ""
    verified = bundle.verified_subject
    # A free-body picture with no result behind it is drawn, not solved.
    solved = verified is not None and not is_picture_only(verified)
    system = "\n\n".join(
        str(m.get("content")) for m in bundle.prompt_messages if m.get("role") == "system"
    )
    return Route(
        photo=photo,
        image_gen=image_gen,
        search=search,
        subject=subject,
        solved=solved,
        instant=_instant_kind(bundle.instant_reply, solved=solved),
        instant_text=bundle.instant_reply or "",
        lightweight=bool(bundle.lightweight),
        model=model,
        hints=_hints_in(system, case),
        system_prompt=system,
        verified_answer=(verified.display_answer or verified.canonical_answer or "")
        if verified
        else "",
        verified_text=verified.text if verified else "",
        picture=bool(
            not photo
            and not image_gen
            and reply_picture_prompt(text, settings)
            and settings.image_generation_enabled
            and can_use(user, "image_generation", settings)
        ),
        settings_card=bundle.settings_card or "",
        after_card=bundle.after_card,
        memory=bool(loaded.get("load_memory")),
        memory_scope=str(loaded.get("memory_scope") or "") if loaded.get("load_memory") else "",
        history_rag=bool(loaded.get("history_rag")),
        server_pictures=_server_pictures(verified),
        trace=trace,
        context=ctx,
    )


def _server_pictures(verified: Any) -> str:
    if verified is None:
        return ""
    specs = [verified.canonical_fence, *verified.canonical_fences]
    return "\n\n".join(
        f"```simulation\n{json.dumps(spec)}\n```"
        for spec in specs
        if isinstance(spec, dict) and spec.get("type") in SIMULATION_SPEC_TYPES
    )


def mismatches(expect: Expect, route: Route) -> list[str]:
    """Each way the route differs from what the case expects."""
    out: list[str] = []

    def check(name: str, want: object, got: object) -> None:
        if want is not None and want != got:
            out.append(f"{name}: expected {want!r}, got {got!r}")

    if expect.photo is not None:
        if expect.photo == "":
            check("photo", "", route.photo)
        elif expect.photo.lower() != route.photo.lower():
            out.append(f"photo: expected {expect.photo!r}, got {route.photo!r}")
    if expect.photo_not:
        words = route.photo.lower().split()
        if not route.photo:
            out.append("photo: expected a lookup, got none")
        for word in expect.photo_not:
            if word in words:
                out.append(f"photo: {route.photo!r} still says {word!r}")
    check("image_gen", expect.image_gen, route.image_gen)
    check("picture", expect.picture, route.picture)
    check("settings_card", expect.settings_card, bool(route.settings_card))
    # An intercepted turn (photo or generated image) never reaches the rest.
    if route.photo or route.image_gen:
        return out
    check("search", expect.search, route.search)
    check("subject", expect.subject, route.subject)
    check("solved", expect.solved, route.solved)
    check("instant", expect.instant, route.instant)
    check("lightweight", expect.lightweight, route.lightweight)
    check("model", expect.model, route.model)
    check("memory", expect.memory, route.memory)
    if expect.memory_scope is not None and route.memory:
        check("memory_scope", expect.memory_scope, route.memory_scope)
    if expect.answer_photo and "answer_photo" not in route.hints:
        out.append("answer photo: the turn never offers one")
    for hint in expect.hints:
        if hint not in route.hints:
            out.append(f"hint {hint!r} missing")
    for hint in expect.no_hints:
        if hint in route.hints:
            out.append(f"hint {hint!r} present")
    return out


@asynccontextmanager
async def _no_session() -> Any:
    yield AsyncMock()


async def _no_reminders(_session: object, **kwargs: Any) -> tuple[str, int]:
    return str(kwargs["assistant_text"]), 0


async def saved_reply(route: Route, settings: Settings | None = None) -> str:
    """The route's instant reply as the turn saves it: through the real finalize passes
    (a subject's fence check among them), with no to-do write. The trace keeps the passes
    that changed it."""
    deps = replace(
        default_deps(),
        session_factory=_no_session,
        users=SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
        todos=SimpleNamespace(materialize_reminder_fences=AsyncMock(side_effect=_no_reminders)),
    )
    return await enrich_final_content(
        deps,
        AsyncMock(),
        settings or battery_settings(),
        route.context,
        assistant_text=route.instant_text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[route.instant_text],
        should_cancel=None,
    )
