from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.schemas.text import UserText

ProductEventName = Literal[
    "paywall_viewed",
    "purchase_started",
    "purchase_succeeded",
    "purchase_failed",
    "push_permission",
    "chat_ttft",
    "chat_turn_outcome",
]


class ProductEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProductEventName
    properties: dict[str, str] = Field(default_factory=dict)
    platform: Literal["ios", "android", "web"] | None = None
    app_version: UserText | None = Field(default=None, max_length=32)
    installation_id: UserText | None = Field(default=None, max_length=128)
    client_at: datetime | None = None

    @field_validator("properties")
    @classmethod
    def validate_property_size(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 8:
            raise ValueError("At most 8 event properties are allowed")
        if any(len(key) > 32 or len(item) > 64 for key, item in value.items()):
            raise ValueError("Event property keys or values are too long")
        return value


class ProductEventBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ProductEventIn] = Field(min_length=1, max_length=20)
