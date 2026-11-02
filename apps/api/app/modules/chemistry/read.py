"""Read a photographed chemistry problem back as plain text.

This is not the math scanner. It does not call Mathpix and it does not ask
for equation, system, or inequality kinds. The student confirms the text,
then the chat solves that text alone.
"""

from __future__ import annotations

from app.core.config import Settings
from app.services.scan_text import read_problem_text

CHEMISTRY_READ_PROMPT = (
    "Read the chemistry problem written in this image. "
    "Return only that problem as plain text. "
    "Do not solve it. Do not describe glassware, apparatus, or a structure. "
    "If there is no written problem, return nothing."
)

_MOCK_READING = "Find the molar mass of H2O"


async def read_chemistry_problem(
    settings: Settings,
    *,
    content_type: str,
    data: bytes,
    timeout_seconds: float | None = None,
) -> str:
    """The written problem, or empty when the page cannot be read."""
    return await read_problem_text(
        settings,
        prompt=CHEMISTRY_READ_PROMPT,
        content_type=content_type,
        data=data,
        mock_reading=_MOCK_READING,
        timeout_seconds=timeout_seconds,
    )
