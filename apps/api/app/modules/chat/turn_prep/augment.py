"""Phase B/C: fetch a verified subject solve, then inject it.

Live web results come from the tool loop, after this; the pre-stream search and
its LLM classifier never ran in production and are gone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.readings import read_off_loop
from app.modules import web_search as web_search_service
from app.modules.chat.prompt_builder import SubjectFetch, fetch_subject, inject_subject_block
from app.modules.chat.turn_prep.followups import (
    SubjectFollowup,
    resolve_subject_followup,
    role_content_dicts,
)
from app.modules.chat.turn_prep.instant import location_not_set_reply
from app.modules.chat.turn_prep.mode import _should_augment_web_and_tools
from app.modules.chat.turn_prep.model_read_shadow import start_model_read_shadow
from app.modules.chat.turn_prep.reading import plan_of
from app.modules.chat.turn_prep.request import TurnIdentity, TurnRequest
from app.modules.chat.whole_question import whole_question_fetch
from app.modules.chat.worked_render import WorkedLayout
from app.modules.chat.worked_turn import with_worked_contract, worked_layout
from app.modules.turn_reading.plan import TurnPlan
from app.modules.web_search.subject import (
    collect_prior_user_messages as _prompt_prior_user_messages,
)
from app.modules.web_search.subject import last_assistant_content
from app.services.solving import VerifiedSolveBlock
from app.services.subjects.dispatch import SubjectName, read_direct_reply, read_subject
from app.services.subjects.registry import subject_adapter

if TYPE_CHECKING:
    from app.services.subjects.registry import MoneyTurn

# Earlier user lines a follow-up may take its problem from.
_PRIOR_USER_LINES = 8


@dataclass
class Augmentation:
    prompt_messages: list[dict[str, str]]
    verified_subject: VerifiedSolveBlock | None = None
    solver_unverified: bool = False
    unverified_subject: str | None = None
    # A reply both halves of a two-part question already rendered.
    direct_text: str | None = None
    # The message asks for more than its solve: the model answers the rest.
    asks_more: bool = False
    # SymPy ran out of time on the turn's problem: the tool loop does not run it again.
    solve_timed_out: bool = False
    # The message's subject, as the subject order read it.
    subject: SubjectName | None = None
    # A calculation nothing verified: the model writes a ```worked block (``worked_turn``).
    worked: WorkedLayout | None = None

    async def direct_reply(
        self, request: TurnRequest, followup: SubjectFollowup, settings: Settings
    ) -> str | None:
        """The reply the verified solve writes itself, when the turn needs no model."""
        if self.direct_text:
            return self.direct_text
        if self.verified_subject is None or self.asks_more:
            return None
        return await read_direct_reply(
            self.verified_subject,
            request.content,
            settings,
            has_image_attachment=request.has_image_attachment,
            verified_request_text=followup.math,
        )


async def gather_and_inject(
    request: TurnRequest,
    identity: TurnIdentity,
    settings: Settings,
    redis: Redis,
    prompt_messages: list[dict[str, str]],
    followup: SubjectFollowup,
    *,
    instant_reply: str | None,
    money: bool = False,
) -> Augmentation:
    """Phase B/C for one turn. A turn the gate turns away keeps its prompt as built.

    A money turn (``turn_prep.money``) has its numbers worked already: no subject solve.
    """
    if money:
        return Augmentation(prompt_messages)
    mode = identity.mode
    plan = plan_of(request.content, settings)
    detected_subject = await read_subject(
        _mixed_solve(plan) or request.content,
        settings,
        has_image_attachment=request.has_image_attachment,
        image_math_extract=request.image_math_extract,
    )
    if instant_reply is None:
        start_model_read_shadow(request.content, settings, redis, subject=detected_subject)
    needs_math, needs_search, needs_chem = _turn_needs(
        request, settings, prompt_messages, followup, plan, detected_subject
    )
    if not _should_augment_web_and_tools(
        instant_reply=instant_reply,
        lightweight=mode.lightweight,
        minimal_personal=mode.minimal_personal,
        day_planning=mode.day_planning,
        ambiguous_nearby=identity.geo.ambiguous_nearby,
        rich_context=mode.rich_context,
        needs_math=needs_math,
        needs_search=needs_search,
        needs_chem=needs_chem,
    ):
        return Augmentation(prompt_messages, subject=detected_subject)

    # Phase B: the subject solve. Phase C: inject it before the last user message.
    with subject_adapter("math").solve_timeouts() as timed_out:
        fetched = await _fetch_subject_with_priors(
            request, identity, settings, redis, prompt_messages, followup, plan
        )
    fetched = _readable_fetch(request, identity, prompt_messages, followup, fetched)
    return Augmentation(
        prompt_messages=inject_subject_block(prompt_messages, fetched.subject_block),
        verified_subject=fetched.verified,
        solver_unverified=fetched.solver_unverified,
        unverified_subject=fetched.unverified_subject,
        direct_text=fetched.direct_text,
        asks_more=plan.multi and any(part.kind != "solve" for part in plan.parts),
        solve_timed_out=bool(timed_out),
        subject=detected_subject,
    )


def _readable_fetch(
    request: TurnRequest,
    identity: TurnIdentity,
    prompt_messages: list[dict[str, str]],
    followup: SubjectFollowup,
    fetched: SubjectFetch,
) -> SubjectFetch:
    """The fetch held to the whole question it answers (``whole_question``): the message,
    the problem a follow-up solves again, and the earlier lines a terse follow-up borrows
    ("graph it" plots the last plottable line; a fragment such as "5" continues the open
    equation). Any of them unread, written in another language or with a number its
    writer's locale reads otherwise, and the result goes."""
    content = request.content
    borrowed: list[str] = []
    if subject_adapter("math").followups.borrows_earlier(content):
        borrowed = _prompt_prior_user_messages(prompt_messages, content)[-_PRIOR_USER_LINES:]
    return whole_question_fetch(
        content,
        fetched,
        locale=identity.user.locale,
        problems=(followup.math, followup.chemistry, followup.physics, *borrowed),
    )


def _mixed_solve(plan: TurnPlan) -> str | None:
    """The one maths, physics or chemistry request of a message that asks for more.

    "Solve 2x + 5 = 17 and also what's the weather in Paris" is solved from its own
    words: the whole line read as one problem lost the verification.
    """
    solves = plan.of_kind("solve")
    return solves[0].text if plan.multi and len(solves) == 1 else None


def _solve_parts(plan: TurnPlan) -> tuple[str, ...]:
    """The separate questions of a message that holds several, each solved on its own:
    "A ball is dropped from 20 m. What is its speed after 1 s? How long does it take to
    reach the ground?" is two (``turn_prep.intents``)."""
    solves = plan.of_kind("solve")
    return tuple(part.text for part in solves) if len(solves) >= 2 else ()


def _turn_needs(
    request: TurnRequest,
    settings: Settings,
    prompt_messages: list[dict[str, str]],
    followup: SubjectFollowup,
    plan: TurnPlan,
    detected_subject: SubjectName | None,
) -> tuple[bool, bool, bool]:
    """Whether the turn needs maths, a web search and chemistry, in that order."""
    content = request.content
    needs_math = settings.math_tools_enabled and (
        detected_subject in {"math", "physics"}
        or followup.math is not None
        or followup.physics is not None
        or subject_adapter("math").followups.continues_alone(content)
    )
    needs_search = web_search_service.needs_web_search(
        content,
        prior_user_messages=_prompt_prior_user_messages(prompt_messages, content) or None,
        prior_assistant=last_assistant_content(prompt_messages),
    ) or (plan.multi and any(web_search_service.needs_web_search(text) for text in plan.texts()))
    needs_chem = settings.chemistry_enabled and (
        detected_subject == "chemistry" or followup.chemistry is not None
    )
    return needs_math, needs_search, needs_chem


async def _fetch_subject_with_priors(
    request: TurnRequest,
    identity: TurnIdentity,
    settings: Settings,
    redis: Redis,
    prompt_messages: list[dict[str, str]],
    followup: SubjectFollowup,
    plan: TurnPlan,
) -> SubjectFetch:
    # Earlier user lines can hold the problem a follow-up refers to. They come from
    # the prompt's own history: a second read of the messages raced the current line.
    priors = _prompt_prior_user_messages(prompt_messages, request.content)[-_PRIOR_USER_LINES:]
    return await fetch_subject(
        request.content,
        settings,
        prior_user_messages=priors,
        has_image_attachment=request.has_image_attachment,
        image_math_extract=request.image_math_extract,
        math_followup_problem=followup.math,
        chemistry_followup_problem=followup.chemistry,
        physics_followup_problem=followup.physics,
        on_status=request.on_status,
        redis=redis,
        subject_text=_mixed_solve(plan),
        parts=_solve_parts(plan),
        parts_answer_all=all(part.kind == "solve" for part in plan.parts),
    )


async def augment_after_prompt(
    request: TurnRequest,
    identity: TurnIdentity,
    settings: Settings,
    redis: Redis,
    prompt_messages: list[dict[str, str]],
    instant_reply: str | None,
    money: MoneyTurn | None,
) -> tuple[Augmentation, str | None]:
    """Phases B and C after the prompt: a follow-up's subject, the verified solve (none for a
    money turn, whose numbers are worked already), and a reply the solve writes itself."""
    followup = (
        await read_off_loop(
            resolve_subject_followup,
            request.content,
            role_content_dicts(prompt_messages),
            timeout=settings.subject_read_timeout_seconds,
        )
        or SubjectFollowup()
    )
    if instant_reply is None:
        instant_reply = location_not_set_reply(request.content, identity.geo, followup)
    augmented = await gather_and_inject(
        request,
        identity,
        settings,
        redis,
        prompt_messages,
        followup,
        instant_reply=instant_reply,
        money=money is not None,
    )
    timing = request.timing
    if timing is not None:
        timing.mark_phase("augment_done")
        timing.mark_prompt_ready()
    if instant_reply is None:
        instant_reply = await augmented.direct_reply(request, followup, settings)
    augmented.worked = worked_layout(
        request.content,
        augmented.subject or _followup_subject(followup),
        settings,
        answered=bool(instant_reply is not None or augmented.verified_subject or money),
        lightweight=identity.mode.lightweight,
        several_requests=plan_of(request.content, settings).multi,
    )
    if augmented.worked is not None:
        augmented.prompt_messages = with_worked_contract(augmented.prompt_messages)
    return augmented, instant_reply


def _followup_subject(followup: SubjectFollowup) -> SubjectName | None:
    """The subject of the earlier problem a follow-up solves again."""
    if followup.physics is not None:
        return "physics"
    if followup.chemistry is not None:
        return "chemistry"
    return "math" if followup.math is not None else None
