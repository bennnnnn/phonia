"""Where a provider may cache a chat prompt, for the models that cache only a marked prefix.

A chat prompt opens with two system messages (``modules/chat/prompt_builder``): the
stable one, the same text on every turn for this user (who Recall is, the tone and
unclear-message rules, their own instructions and language), then the rules this kind
of turn needs; the history and what changes on every turn follow. Most providers reuse
the longest prefix they have seen by themselves. A model flagged ``cache_breakpoints``
(Anthropic's) caches only up to a ``cache_control`` mark, so its stable message goes as
one text part carrying the mark: OpenRouter's format, which LiteLLM forwards for Claude.
Only that message is marked: the rules differ between a slim and a rich turn, and a
mark that is not read again pays the cache write (1.25x) for nothing.
"""

from __future__ import annotations

from typing import Any

from app.models.model_catalog import ChatModel

# The cache lifetime every caching provider offers; it renews on each hit.
EPHEMERAL = {"type": "ephemeral"}


def with_cache_breakpoint(
    messages: list[dict[str, Any]], route: ChatModel, *, enabled: bool = True
) -> list[dict[str, Any]]:
    """``messages`` with the stable system message marked, when ``route`` needs the mark.

    ``enabled`` is the ``prompt_cache_breakpoints_enabled`` setting. Only a stable
    message followed by the turn's own system message is marked: a lone system prompt
    holds that turn's text too, and a mark on it would pay a cache write on every turn
    and never be read. The messages are not changed in place.
    """
    if not enabled or not route.cache_breakpoints or len(messages) < 2:
        return messages
    stable, turn = messages[0], messages[1]
    text = stable.get("content")
    if stable.get("role") != "system" or turn.get("role") != "system":
        return messages
    if not isinstance(text, str) or not text:
        return messages
    part = {"type": "text", "text": text, "cache_control": dict(EPHEMERAL)}
    return [{**stable, "content": [part]}, *messages[1:]]
