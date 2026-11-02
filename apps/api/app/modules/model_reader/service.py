"""The model reader: two short calls, the server's checks, and the subject's own binder.

``read_with_model`` asks a model which subject and kind of law a question is (one call),
then which law of that kind and the values it states (a second call, with that kind's
laws only). The read becomes an intent only when ``checks.check_read`` finds every value
in the message and the subject's binder reads it back to the same law and values
(``physics.model_read``, ``chemistry.model_read``). Maths keeps its own typed read
(``math.tools.llm_extract``). Nothing here raises into a turn; a failure is a reason.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from app.core.config import Settings
from app.core.sympy_executor import get_sympy_executor, run_sympy
from app.models.routing_lanes import ROUTING
from app.modules.chemistry.model_read import chemistry_menu, chemistry_read_intent
from app.modules.math.tools.llm_extract import llm_extract_math_intent
from app.modules.model_reader.checks import check_read
from app.modules.model_reader.prompts import law_prompt, route_prompt
from app.modules.model_reader.schemas import MATH_TASKS, LawRead, ModelRead, Reason, RouteRead
from app.modules.physics.model_read import physics_menu, physics_read_intent
from app.services.law_binding.model_read import Stated

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 1500
# The binder reads one short English sentence: far below any solve.
_BIND_SECONDS = 2.0


@lru_cache(maxsize=1)
def _route_prompt() -> str:
    return route_prompt(physics_menu(), chemistry_menu(), list(MATH_TASKS))


async def _ask[T: LawRead | RouteRead](
    settings: Settings, system: str, text: str, schema: type[T], usage: dict[str, int]
) -> T | None:
    # Imported here: SymPy pool workers import the subjects, not the gateway (190 MB).
    from app.gateways.structured_completion import complete_structured

    return await complete_structured(
        settings=settings,
        model_alias=ROUTING.math_extract,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
        schema=schema,
        max_tokens=400,
        timeout_seconds=settings.model_reader_timeout_seconds,
        usage=usage,
        allow_fallback=False,
        quiet_timeout=True,
    )


async def read_with_model(text: str, settings: Settings) -> ModelRead:
    """What a model reads ``text`` to ask, checked; never raises."""
    started = time.perf_counter()
    usage: dict[str, int] = {}

    def done(
        subject: str | None, op: str | None, intent: object | None, reason: Reason
    ) -> ModelRead:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        tokens = int(usage.get("input", 0)), int(usage.get("output", 0))
        return ModelRead(subject, op, intent, reason, elapsed, *tokens)

    question = text.strip()[:_MAX_INPUT_CHARS]
    if not question:
        return done(None, None, None, "no_read")
    try:
        route = await _ask(settings, _route_prompt(), question, RouteRead, usage)
        if route is None:
            return done(None, None, None, "no_read")
        if route.subject == "none":
            return done(None, None, None, "not_subject")
        if route.subject == "math":
            task = MATH_TASKS.get(route.kind or "")
            if task is None:
                return done("math", None, None, "other_task")
            intent = await llm_extract_math_intent(
                question,
                settings,
                usage=usage,
                timeout_seconds=settings.model_reader_timeout_seconds,
                alone=True,
            )
            if intent is None:
                return done("math", None, None, "no_read")
            kind, operation = task
            # The typed read must be the task the question was routed as, never a near one.
            if intent.kind != kind or (operation is not None and intent.operation != operation):
                return done("math", intent.kind, None, "kind_mismatch")
            return done("math", intent.kind, intent, "ok")
        menu = physics_menu() if route.subject == "physics" else chemistry_menu()
        cards = menu.get(route.kind or "")
        if not cards:
            return done(route.subject, None, None, "unknown_kind")
        read = await _ask(settings, law_prompt(route.subject, cards), question, LawRead, usage)
        if read is None or read.op == "none":
            return done(route.subject, None, None, "no_read")
        if read.op not in {card.op for card in cards}:
            return done(route.subject, None, None, "unknown_op")
        checked = check_read(question, read)
        if checked != "ok":
            return done(route.subject, read.op, None, checked)
        stated = [Stated(given.name, given.value, given.unit, given.quote) for given in read.givens]
        # The binder is a subject reader: in the SymPy pool (CLAUDE.md rule 7), and only
        # with a slot to spare, so a shadow read never makes the turn's own solve wait.
        free = get_sympy_executor().free_slots()
        if free is not None and free < 2:
            return done(route.subject, read.op, None, "pool_busy")
        bound: object | None
        if route.subject == "physics":
            bound = await run_sympy(
                physics_read_intent, read.op, stated, question, timeout=_BIND_SECONDS
            )
        else:
            bound = await run_sympy(
                chemistry_read_intent,
                read.op,
                stated,
                read.formula,
                question,
                timeout=_BIND_SECONDS,
            )
        if bound is None:
            return done(route.subject, read.op, None, "binder_disagrees")
        return done(route.subject, read.op, bound, "ok")
    except Exception as exc:
        logger.info("model read failed (%s)", type(exc).__name__)
        return done(None, None, None, "failed")
