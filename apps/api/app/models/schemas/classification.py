"""What a small model call returns about the conversation (validated before use, Golden Rule 6)."""

from pydantic import BaseModel, Field


class ConversationReference(BaseModel):
    """What a follow-up like "do a search" or "show me her image" refers to."""

    text: str | None = Field(
        default=None,
        max_length=160,
        description="Standalone search query or photo subject; null when unclear",
    )
