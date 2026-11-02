from typing import Literal

from pydantic import BaseModel

MessageRole = Literal["user", "assistant", "system"]

MemoryType = Literal["profile", "preference", "project", "fact", "focus"]

MemoryStatus = Literal["active", "superseded", "muted"]

MemorySensitivity = Literal[
    "normal",
    "health",
    "finance",
    "legal",
    "relationship",
    "identity",
    "highly_sensitive",
]

MemoryOpKind = Literal["add", "update", "supersede", "delete", "mute"]


ResponseTone = Literal["funny", "professional", "casual", "soft"]
EmojiUse = Literal["off", "some", "more"]

# Voices both read-aloud (gpt-4o-mini-tts) and live talk (realtime) can speak,
# so one choice sounds the same in both.
UserVoice = Literal[
    "marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"
]

MessageFeedback = Literal["up", "down"]


class UsageOut(BaseModel):
    date: str
    input_tokens: int
    output_tokens: int
    daily_limit: int
    used_tokens: int
    remaining: int
    context_token_budget: int
    recent_message_window: int


class ModelInfo(BaseModel):
    id: str
    label: str
    description: str
    tier: str
    plan_access: str = "pro"
    available: bool
    input_price_per_m: float | None = None
    output_price_per_m: float | None = None
    quota_multiplier: float = 1.0
    healthy: bool = True
    latency_p50_ms: int | None = None
    health_samples: int = 0
