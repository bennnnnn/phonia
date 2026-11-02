"""Image generation MCP adapter — model-callable when the tool loop is on.

Persists the attachment + assistant ``[Image: …]`` marker and signals a
terminal turn via ``ToolResult.data`` so the stream skips the visible LLM
pass (never trust the model to invent attachment URLs).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.gateways.mcp.base import ToolContext, ToolResult
from app.models.schemas.tools import GenerateImageToolInput
from app.modules.billing import can_use
from app.modules.images import generation as image_generation_service
from app.modules.images.tool_result import terminal_image_result

logger = logging.getLogger(__name__)


class ImageGenAdapter:
    name = "generate_image"
    input_schema = GenerateImageToolInput

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def describe(self) -> str:
        return (
            "Generate or edit a picture for the user and attach it to this chat. "
            "For edits, pass reference_attachment_ids from the user's images; never invent IDs. "
            "Call ONLY when they clearly want a visual image/illustration/photo "
            "(e.g. draw a cat, create a sunset pic). "
            "Do NOT use for math examples, equations, quizzes, code, todos, "
            "diagrams/charts (use sympy), or ordinary chat follow-ups."
        )

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.describe(),
                "parameters": GenerateImageToolInput.model_json_schema(),
            },
        }

    async def invoke(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return ToolResult(name=self.name, content="Missing prompt.")

        user = ctx.user
        chat_id = ctx.chat_id
        if user is None or chat_id is None:
            return ToolResult(
                name=self.name,
                content="Image generation is unavailable in this context.",
            )
        if not self.settings.image_generation_enabled:
            return ToolResult(name=self.name, content="Image generation is disabled.")
        if not can_use(user, "image_generation", self.settings):
            return ToolResult(
                name=self.name,
                content="Image generation is not part of this user's plan.",
            )

        aspect = args.get("aspect_ratio")
        aspect_ratio = aspect if isinstance(aspect, str) else None

        try:
            # User row already exists from turn prep — only write the assistant
            # image marker. Keyword / HTTP paths may still create both.
            _user_msg, asst_msg = await image_generation_service.generate_for_chat(
                self.settings,
                user=user,
                chat_id=chat_id,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                create_user_message=False,
                reference_attachment_ids=(
                    [UUID(str(value)) for value in args["reference_attachment_ids"]]
                    if args.get("reference_attachment_ids")
                    else None
                ),
            )
        except image_generation_service.ImageGenerationError as exc:
            return ToolResult(
                name=self.name,
                content=f"Image generation failed: {exc.detail}",
            )
        except Exception:
            logger.exception("Image generation tool failed chat_id=%s", chat_id)
            return ToolResult(
                name=self.name,
                content="Image generation failed unexpectedly.",
            )

        return terminal_image_result(
            self.name,
            asst_msg,
            attached=(
                "Image generated. The app will show it — do not invent URLs or write another reply."
            ),
            no_marker="Image generation did not produce an attachment marker.",
            default_model="image-gen-model",
        )
