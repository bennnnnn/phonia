"""Voice (dictation, read-aloud)."""

from pydantic import BaseModel


class MediaSettings(BaseModel):
    speech_transcription_enabled: bool = True
    # Direct OpenAI voice. Empty overrides use the speech catalog aliases.
    speech_transcription_model: str = ""
    speech_rate_limit_per_minute: int = 10
    # Cloud TTS (read-aloud). Operator override (OpenAI model); empty →
    # catalog alias `speech-tts-model`.
    speech_tts_enabled: bool = True
    speech_tts_model: str = ""
    speech_tts_voice: str = ""
