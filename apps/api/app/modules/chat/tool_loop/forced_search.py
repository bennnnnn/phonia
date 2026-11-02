"""The live search a turn needs when the model skipped ``web_search``."""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from typing import Any

from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.gateways.mcp.base import ToolContext
from app.gateways.web_search_gateway import WebSearchHit
from app.modules.chat.stream_status import StreamStatusFn, clip_status_detail
from app.modules.chat.tool_loop.parts import live_parts, open_parts
from app.modules.chat.tool_loop.selection import last_user_content
from app.modules.web_search import (
    format_search_block,
    format_search_empty_block,
    run_cached_search,
    search_queries_for_turn,
    wants_dated_results,
)

logger = logging.getLogger(__name__)

# The longest a forced search may take when the turn has no budget of its own.
_FORCED_SEARCH_MAX_SECONDS = 15.0


def _web_search_was_called(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            name = str((call.get("function") or {}).get("name") or "")
            if name == "web_search":
                return True
    return False


async def _force_web_search_if_needed(
    *,
    settings: Settings,
    messages: list[dict[str, Any]],
    search_hits: list[WebSearchHit],
    ctx: ToolContext,
    on_status: StreamStatusFn | None,
    should_cancel: Callable[[], bool] | None,
    search_required: bool = False,
    search_parts: list[str] | None = None,
    has_verified_math: bool = False,
) -> tuple[list[dict[str, Any]], list[WebSearchHit]]:
    """If the model skipped web_search on a turn that needs live results, search once.

    ``search_required`` preserves a classifier-yes decision. The sync heuristic
    alone would otherwise drop that turn (silent answer from training data).
    Empty hits still inject a no-results block so the model cannot look current.
    A message with more than one request searches each live part for itself:
    "I need a laptop, and I also want remote backend jobs" searches the jobs.
    """
    if search_hits:
        return messages, search_hits
    if should_cancel and should_cancel():
        return messages, search_hits
    if not settings.web_search_enabled:
        return messages, search_hits
    user_text = last_user_content(messages)
    if not user_text:
        return messages, search_hits
    from app.modules.chat.prompt_inject import inject_before_last_user
    from app.services.prompt_safety import wrap_untrusted

    already_searched = _web_search_was_called(messages)
    targets = search_parts or live_parts(
        open_parts(user_text, has_verified_math=has_verified_math, settings=settings)
    )
    if not search_required and not already_searched and not targets:
        return messages, search_hits

    tried = [user_text]
    if not already_searched:
        # Show the search before reading the chat for a follow-up's topic.
        if on_status is not None:
            await on_status("searching", None)
        try:
            # What is left of the turn's tool budget; a search that outlives it is a
            # failed search, said so in the prompt, not a minute of "Searching…".
            async with asyncio.timeout(ctx.seconds_left(_FORCED_SEARCH_MAX_SECONDS)):
                hits, tried = await _search_targets(
                    settings, messages, ctx, targets or [user_text], on_status
                )
        except TimeoutError:
            logger.warning("Forced web search ran out of the turn's tool budget")
            ctx.tavily_budget.record_search(failed=True)
            hits, tried = [], targets or [user_text]
        if hits:
            block = wrap_untrusted(
                "web search", format_search_block(hits, user_timezone=ctx.user_timezone)
            )
            return inject_before_last_user(messages, block), hits

    empty = format_search_empty_block(tried or [user_text], failed=ctx.tavily_budget.search_failed)
    return inject_before_last_user(messages, empty), search_hits


async def _search_targets(
    settings: Settings,
    messages: list[dict[str, Any]],
    ctx: ToolContext,
    targets: list[str],
    on_status: StreamStatusFn | None,
) -> tuple[list[WebSearchHit], list[str]]:
    """Each target's best query, searched side by side on the turn's one budget.

    "do a search" / "when did she die?" search for what the chat was about, not for
    the words of the request. Hits alternate between targets, so a part with many
    results cannot crowd out another's.
    """
    query_lists = await gather_or_cancel(
        *(
            search_queries_for_turn(
                settings,
                target,
                messages,
                user_timezone=ctx.user_timezone,
                user_location=ctx.user_location,
            )
            for target in targets
        )
    )
    if on_status is not None:
        first = query_lists[0][0] if query_lists[0] else targets[0]
        await on_status("searching", clip_status_detail(first))
    if len(targets) == 1:
        found = query_lists[0] or targets
        return await run_cached_search(
            settings,
            found,
            user=ctx.user,
            redis=ctx.redis,
            budget=ctx.tavily_budget,
            # The user's own words decide: a rewritten query ("… near Austin, Texas")
            # no longer says it was a search for places near them.
            dated=wants_dated_results(targets[0]),
        )
    queries = [
        found[0] if found else target for found, target in zip(query_lists, targets, strict=True)
    ]
    results = await gather_or_cancel(
        *(
            run_cached_search(
                settings,
                [query],
                user=ctx.user,
                redis=ctx.redis,
                budget=ctx.tavily_budget,
                dated=wants_dated_results(target),
            )
            for query, target in zip(queries, targets, strict=True)
        )
    )
    return _interleave([hits for hits, _tried in results], settings), queries


def _interleave(per_target: list[list[WebSearchHit]], settings: Settings) -> list[WebSearchHit]:
    limit = max(1, min(settings.web_search_max_results, 10))
    merged: list[WebSearchHit] = []
    seen: set[str] = set()
    for row in itertools.zip_longest(*per_target):
        for hit in row:
            key = (hit.url if hit else "").strip().lower()
            if hit is None or key in seen:
                continue
            seen.add(key)
            merged.append(hit)
    # A dated search's news pages come on top of the general results, never in their place.
    dated = sum(1 for hit in merged if hit.published)
    return merged[: max(limit + dated, len(per_target))]
