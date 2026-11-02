"""Reference-photo lookup MCP adapter — model-callable when the tool loop is on.

Distinct from ``ImageGenAdapter``: this returns a *real* photo (Tavily image
search, mirrored into Recall's storage), never AI-generated art. Persists
the attachment + assistant ``[Image: …]`` marker and signals a terminal turn
via ``ToolResult.data`` — same terminal-image contract the chat tool loop
already understands, so the stream skips the visible LLM pass and the
mobile client renders it with zero new code (never trust the model to
invent attachment URLs).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.gateways.mcp.base import ToolContext, ToolResult
from app.models.schemas.tools import ImageSearchToolInput
from app.modules.images import search as image_search_service
from app.modules.images.lookup_intent import names_a_drawing
from app.modules.images.tool_result import terminal_image_result

logger = logging.getLogger(__name__)


class ImageSearchAdapter:
    name = "search_image"
    input_schema = ImageSearchToolInput

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def describe(self) -> str:
        return (
            "Find and attach a REAL reference photo from the web — for "
            "'show me an ear', 'what does a golden retriever look like', "
            "'what does the Eiffel Tower look like', 'show me her image'. Call this "
            "when the user wants to see what something or someone real actually "
            "looks like. The query names the subject itself: a person's full name "
            "or the thing from the conversation, never 'her', 'him' or 'it'. "
            "Do NOT use for creative/artistic requests (draw, paint, create "
            "an image of) — use generate_image for those instead."
        )

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.describe(),
                "parameters": ImageSearchToolInput.model_json_schema(),
            },
        }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult(name=self.name, content="Missing query.")
        if names_a_drawing(query):
            return ToolResult(
                name=self.name,
                content=(
                    "No photo search for molecules, written formulas, equations or graphs: Recall "
                    "draws those. Answer in your reply instead."
                ),
            )

        user = ctx.user
        chat_id = ctx.chat_id
        if user is None or chat_id is None:
            return ToolResult(
                name=self.name,
                content="Reference-photo lookup is unavailable in this context.",
            )
        if not self.settings.image_search_enabled:
            return ToolResult(name=self.name, content="Reference-photo lookup is disabled.")

        try:
            # User row already exists from turn prep — only write the
            # assistant image marker, same as ImageGenAdapter.
            _user_msg, asst_msg = await image_search_service.search_and_attach_for_chat(
                self.settings,
                user=user,
                chat_id=chat_id,
                query=query,
                create_user_message=False,
            )
        except image_search_service.ImageSearchError as exc:
            return ToolResult(name=self.name, content=f"Photo lookup failed: {exc.detail}")
        except Exception:
            logger.exception("Photo lookup tool failed chat_id=%s", chat_id)
            return ToolResult(name=self.name, content="Photo lookup failed unexpectedly.")

        return terminal_image_result(
            self.name,
            asst_msg,
            attached=(
                "Reference photo found and attached. The app will show it — "
                "do not invent URLs or write another reply."
            ),
            no_marker="Photo lookup did not produce an attachment marker.",
            default_model="image-search-model",
        )
