"""Model-initiated MCP tool rounds via LiteLLM ``tools=``.

When ``mcp_tool_loop_enabled`` is on, run bounded non-streaming tool rounds
before the user-visible stream — **only if the turn likely needs a tool**.
Ordinary Q&A streams immediately. After tools run, the visible answer is
**streamed** (tools omitted) — we do not dump a leftover completion as one
chunk, and we do not throw it away and call the model a third time.

- ``selection`` — does the turn need the loop, and which tools may it offer
- ``rounds`` — search first, or one selection round, then hand off to the stream
- ``calls`` — answer each call: refuse it, or run it and check it against the user
- ``results`` — what a call hands back (verified fences, search hits, a terminal image)
- ``text_calls`` — a call the provider wrote into the reply text
- ``forced_search`` — the live search the model skipped
"""

from app.modules.chat.tool_loop.rounds import run_tool_rounds
from app.modules.chat.tool_loop.selection import spent_tools, turn_needs_tool_loop

__all__ = ["run_tool_rounds", "spent_tools", "turn_needs_tool_loop"]
