"""Test helper: run the maths prompt augmentation and splice its block into the messages.

Production builds the block with ``build_math_augmentation`` and injects it itself; tests use
this to see the prompt a turn would send.
"""

from __future__ import annotations

from app.core.config import Settings
from app.modules.chat.prompt_inject import inject_before_last_user
from app.modules.math.schemas import MathImageExtract
from app.modules.math.tools import prompt as math_prompt
from app.modules.math.tools.block import VerifiedMathBlock


async def augment_prompt_messages(
    messages: list[dict[str, str]],
    user_content: str,
    settings: Settings,
    *,
    has_image_attachment: bool = False,
    image_math_extract: MathImageExtract | None = None,
    prior_user_messages: list[str] | None = None,
) -> tuple[list[dict[str, str]], VerifiedMathBlock | None]:
    block, verified = await math_prompt.build_math_augmentation(
        user_content,
        settings,
        has_image_attachment=has_image_attachment,
        image_math_extract=image_math_extract,
        prior_user_messages=prior_user_messages,
    )
    if block is None:
        return messages, None
    return inject_before_last_user(messages, block), verified
