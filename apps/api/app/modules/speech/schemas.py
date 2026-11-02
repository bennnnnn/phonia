"""Speech request and response models."""

from datetime import datetime

from pydantic import BaseModel, Field

# Decoded audio cap. Router and transcribe_audio must use this same value
# so a 6MB clip is 413, not a service None → 502 after quota reserve.
SPEECH_MAX_AUDIO_BYTES = 5_000_000
SPEECH_MAX_B64_CHARS = 4 * ((SPEECH_MAX_AUDIO_BYTES + 2) // 3)
SPEECH_MAX_REQUEST_BYTES = SPEECH_MAX_B64_CHARS + 4096


class SpeechTranscriptionOut(BaseModel):
    text: str


class SpeechTranscriptionIn(BaseModel):
    audio_base64: str = Field(max_length=SPEECH_MAX_B64_CHARS)
    filename: str = "speech.m4a"
    language: str | None = Field(default=None, max_length=16)


class SpeechTtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(default=None, max_length=16)
    model: str | None = Field(default=None, max_length=64)
    # "lead" + one or more "rest" clips are one user tap: reserve quota on lead only.
    part: str | None = Field(default="full", max_length=8)
    # SHA-256 prefix of the lead clip text. Required for unbilled ``rest``.
    lead_hash: str | None = Field(default=None, max_length=64)


class SpeechTtsOut(BaseModel):
    audio_base64: str
    content_type: str = "audio/mpeg"
    model: str = "speech-tts-model"
    lead_hash: str | None = None


class SpeechLiveStatusOut(BaseModel):
    """Live talk for this user. ``remaining`` / ``limit`` are whole minutes this
    UTC month; the ``*_seconds`` fields are exact."""

    enabled: bool
    entitled: bool
    remaining: int
    limit: int
    remaining_seconds: int = 0
    limit_seconds: int = 0
    min_session_seconds: int = 0
    resets_at: datetime | None = None
