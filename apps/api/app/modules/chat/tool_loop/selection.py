"""Does this turn need the tool loop, and which tools may its round offer?

Heuristic SymPy and Tavily already inject on the prompt path, so the pre-stream
selection round only runs when the message still looks like search, unsolved
math, a photo lookup or Pro image generation. Only the user's own words decide:
web results, file text and other context the model reads never do.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.gateways.mcp import registry as mcp_registry
from app.models.orm import User
from app.modules.billing import plan as plan_service
from app.modules.chat.tool_loop.parts import live_parts, open_parts


def last_user_content(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            return content.strip() if isinstance(content, str) else ""
    return ""


def user_words(messages: list[dict[str, Any]], user_text: str | None) -> list[str]:
    """What the user wrote, newest first: this turn, then earlier turns."""
    texts = [user_text.strip()] if user_text and user_text.strip() else []
    earlier = [
        msg["content"]
        for msg in messages
        if msg.get("role") == "user" and isinstance(msg.get("content"), str)
    ]
    if not texts and earlier:
        texts.append(earlier.pop().strip())
    elif earlier:
        earlier.pop()  # the current turn, already first
    texts.extend(text for text in reversed(earlier) if text.strip())
    return texts


def _has_whole_word(lower: str, word: str) -> bool:
    start = 0
    n = len(word)
    length = len(lower)
    while True:
        idx = lower.find(word, start)
        if idx == -1:
            return False
        before_ok = idx == 0 or not lower[idx - 1].isalpha()
        after_ok = idx + n == length or not lower[idx + n].isalpha()
        if before_ok and after_ok:
            return True
        start = idx + 1


def spent_tools(*, solve_timed_out: bool, photo_missed: bool) -> frozenset[str]:
    """The tools a turn's own pre-work already ran without an answer, which its
    loop does not offer again: SymPy that ran out of time on the problem, a photo
    search that found none. Either would only fail the same way a round later."""
    spent = {"sympy"} if solve_timed_out else set()
    if photo_missed:
        spent.add("search_image")
    return frozenset(spent)


def leftover_math_after_verified(content: str) -> bool:
    """Heuristic SymPy took one clause; the user still asked for another.

    Skip the MCP loop only for a single-clause verified ask. Graph + solve
    (or a second ``=`` next to a graph cue) still needs tools.
    """
    lower = content.lower()
    has_viz = any(_has_whole_word(lower, w) for w in ("graph", "plot", "sketch"))
    has_solve = _has_whole_word(lower, "solve")
    if has_viz and has_solve:
        return True
    if has_viz and lower.count("=") >= 2:
        return True
    return False


def turn_needs_tool_loop(
    content: str,
    *,
    lightweight: bool = False,
    has_instant_reply: bool = False,
    has_verified_math: bool = False,
    has_search_sources: bool = False,
    web_search: bool | None = None,
    settings: Settings | None = None,
    user: User | None = None,
    skip_tools: frozenset[str] = frozenset(),
) -> bool:
    """True when a pre-stream ``complete_with_tools`` round is worth the TTFT cost.

    Heuristic SymPy / Tavily already inject on the prompt path. Paying a full
    non-streaming LLM round on every other turn (then discarding the answer and
    streaming a second call) is what made ordinary chat sit on typing dots for
    ~6s. Skip unless this message still looks like search, unsolved math,
    or Pro image gen.

    ``web_search``: optional classifier override (None = sync heuristic).
    ``skip_tools``: tools the turn already spent (``spent_tools``), no reason to loop.
    """
    if settings is not None and not settings.mcp_tool_loop_enabled:
        return False
    if has_instant_reply:
        return False
    text = content.strip() if isinstance(content, str) else ""
    if not text:
        return False
    if lightweight:
        return False
    # A compound graph+solve request still needs the tool loop even when the
    # complete-request audit correctly declined the partial deterministic
    # intent. Requiring a second extraction here would turn that safe decline
    # into a silent "no tools" result.
    if "sympy" not in skip_tools and leftover_math_after_verified(text):
        return True
    # A verified solve closes its own request only: "solve 2x + 5 = 17 and also
    # what's the weather in Paris" still needs the weather searched.
    parts = open_parts(text, has_verified_math=has_verified_math, settings=settings)
    if not parts:
        return False
    if web_search is True:
        return True
    if web_search is not False and not has_search_sources and live_parts(parts):
        return True
    return any(_needs_non_web_tool(part, settings, user, skip_tools) for part in parts)


def _user_asks_for_image(text: str, settings: Settings) -> bool:
    """The user's own words ask for a picture (the chat image intercept's rules).

    Only the user's message counts: web results, file text and other context
    the model reads must never decide to spend the user's image allowance.
    """
    from app.modules.images.gen_intent import extract_image_gen_prompt, stem_subject_claims

    return bool(
        text
        and extract_image_gen_prompt(text)
        and not stem_subject_claims(text, chemistry_enabled=settings.chemistry_enabled)
    )


def _needs_non_web_tool(
    text: str,
    settings: Settings | None,
    user: User | None,
    skip_tools: frozenset[str] = frozenset(),
) -> bool:
    """Math, a photo lookup, or image generation still needs a tool-selection round."""
    from app.modules.images.lookup_intent import extract_image_lookup_query
    from app.services.subjects.registry import subject_adapter

    sympy_on = "sympy" not in skip_tools
    if sympy_on and leftover_math_after_verified(text):
        return True
    from app.modules.turn_reading.coding import has_code_syntax

    math_on = sympy_on and (settings is None or settings.math_tools_enabled)
    # A pasted traceback or loop is code to read, not an equation for SymPy.
    maths = subject_adapter("math")
    if math_on and not has_code_syntax(text) and maths.asks(text):
        # Detection without an extractor is the 7*8 trap: the sympy tool
        # calls the same extractor and burns the round timeout for nothing.
        if maths.reads(text):
            return True
    # Reference-photo lookup ("show me an ear") is checked before generation
    # so its disjoint trigger phrasing (show / let … see / what does … look
    # like) never competes with generation's own verbs — see
    # image_lookup_intent's module docstring.
    lookup_on = "search_image" not in skip_tools and (
        settings is None or settings.image_search_enabled
    )
    if lookup_on and extract_image_lookup_query(text):
        return True
    image_on = settings is None or settings.image_generation_enabled
    resolved = settings or get_settings()
    if (
        image_on
        and user is not None
        and plan_service.can_use(user, "image_generation", resolved)
        and _user_asks_for_image(text, resolved)
    ):
        return True
    return False


def _search_before_the_model(
    user_text: str,
    settings: Settings,
    user: User | None,
    *,
    web_search: bool | None,
    has_verified_math: bool = False,
    skip_tools: frozenset[str] = frozenset(),
) -> bool:
    """True when the reply only needs sources, so the selection model can be skipped."""
    if not settings.web_search_enabled or not user_text:
        return False
    parts = open_parts(user_text, has_verified_math=has_verified_math, settings=settings)
    if any(_needs_non_web_tool(part, settings, user, skip_tools) for part in parts or [user_text]):
        return False
    if web_search is True:
        return True
    if web_search is False:
        return False
    return bool(live_parts(parts or [user_text]))


def _tools_for_user(
    settings: Settings,
    user: User | None,
    *,
    user_text: str = "",
    skip_tools: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """OpenAI tool payloads for this turn, less the ones it already spent.

    Image generation is offered only when it is on, in the user's plan, and
    *user_text* (the user's own message) asks for a picture.
    """
    tools = [
        tool
        for tool in mcp_registry.build_openai_tools()
        if (tool.get("function") or {}).get("name") not in skip_tools
    ]
    from app.modules.chat.turn_prep.reading import plan_of

    if not settings.image_search_enabled or plan_of(user_text, settings).multi:
        # A photo ends the turn, and a message with more than one request must
        # still get its other answers: its photo comes above the reply instead.
        tools = [t for t in tools if (t.get("function") or {}).get("name") != "search_image"]
    if (
        settings.image_generation_enabled
        and user is not None
        and plan_service.can_use(user, "image_generation", settings)
        and _user_asks_for_image(user_text, settings)
    ):
        return tools
    return [t for t in tools if (t.get("function") or {}).get("name") != "generate_image"]
