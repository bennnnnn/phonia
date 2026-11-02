import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.models.schemas.text import UserText

# What Expo's push service issues: ExponentPushToken[...] (older SDKs: ExpoPushToken[...]).
_EXPO_TOKEN = re.compile(r"Expo(?:nent)?PushToken\[[A-Za-z0-9_-]{1,256}\]")


def _expo_token(value: str) -> str:
    if not _EXPO_TOKEN.fullmatch(value):
        raise ValueError("not an Expo push token")
    return value


ExpoPushToken = Annotated[
    UserText, Field(min_length=8, max_length=512), AfterValidator(_expo_token)
]


class PushTokenIn(BaseModel):
    expo_push_token: ExpoPushToken
    platform: UserText = Field(min_length=2, max_length=20)
    device_id: UserText | None = Field(default=None, max_length=128)
    # "split" created the first three channels. "tone" created the v2 channels
    # that play the bundled cue. Older installs omit this.
    android_channels: Literal["split", "tone"] | None = None


class PushTokenDeleteIn(BaseModel):
    """Turning push off names only the token: the phone has no platform to send."""

    expo_push_token: ExpoPushToken
