"""The turn's verified block after the tool loop's own solve."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.modules.chat.whole_question import answers_with
from app.services.solving import VerifiedMathBlock


def with_tool_verified(server: Any, tool: Any, question: str, locale: str | None = None) -> Any:
    """The turn's verified block after the tool loop.

    A block the server built from the user's own text is never replaced by one
    the model's tool call produced: the model may have mistyped the problem.
    A maths block may gain a diagram the server did not draw; its answer stays.
    The tool's block is held to the question as the server's is: a card the gate
    dropped from the server's solve never comes back through the model's call, and a
    question the readers cannot read (``locale`` is its writer's) gets none from it.
    """
    if server is None:
        return tool if answers_with(question, tool, locale=locale) else None
    if not isinstance(server, VerifiedMathBlock) or not isinstance(tool, VerifiedMathBlock):
        return server
    kinds = {
        fence.get("type") for fence in (server.canonical_fence, *server.canonical_fences) if fence
    }
    kinds.add("answer")
    extra: list[dict[str, Any]] = []
    for fence in (tool.canonical_fence, *tool.canonical_fences):
        if fence and fence.get("type") not in kinds:
            kinds.add(fence.get("type"))
            extra.append(fence)
    if not extra:
        return server
    return replace(server, canonical_fences=[*server.canonical_fences, *extra])
