"""Speech-to-text and TTS product services (validation + mock; HTTP in gateways)."""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.gateways import mock_llm, speech_gateway
from app.models.model_catalog import openrouter_slug
from app.modules.speech.schemas import SPEECH_MAX_AUDIO_BYTES
from app.modules.speech.transcript_validation import sanitize_transcript

logger = logging.getLogger(__name__)

_MAX_TTS_CHARS = 4000
_MOCK_MP3_BYTES = b"\xff\xfb\x90\x00" + b"\x00" * 64

_STT_ALIAS = "speech-stt-model"
TTS_QUALITY_ALIAS = "speech-tts-model"
TTS_FAST_ALIAS = "speech-tts-fast-model"
LIVE_TALK_ALIAS = "live-talk-model"
_OPENAI_TTS_VOICES = frozenset(
    {
        "alloy",
        "echo",
        "fable",
        "onyx",
        "nova",
        "shimmer",
        "ash",
        "ballad",
        "coral",
        "sage",
        "verse",
        "marin",
        "cedar",
    }
)


def normalize_tts_alias(raw: str | None) -> str:
    alias = (raw or "").strip()
    if alias in {"tts-model", TTS_QUALITY_ALIAS, ""}:
        return TTS_QUALITY_ALIAS
    if alias == TTS_FAST_ALIAS:
        return TTS_FAST_ALIAS
    return TTS_QUALITY_ALIAS


def resolve_tts_model(settings: Settings, *, alias: str | None = None) -> str:
    """Both read-aloud aliases use OpenAI; ignore stale non-OpenAI overrides."""
    chosen = normalize_tts_alias(alias)
    if chosen == TTS_FAST_ALIAS:
        return openrouter_slug(TTS_FAST_ALIAS)
    raw = (settings.speech_tts_model or openrouter_slug(TTS_QUALITY_ALIAS)).strip()
    if speech_gateway.can_speak_with(raw):
        return raw
    return openrouter_slug(TTS_QUALITY_ALIAS)


def resolve_tts_voice(settings: Settings, model: str, user_voice: str | None = None) -> str:
    """The user's voice, else the configured one; never one left from Gemini/Kokoro."""
    chosen = (user_voice or "").strip().lower()
    if chosen in _OPENAI_TTS_VOICES:
        return chosen
    voice = (settings.speech_tts_voice or "").strip().lower()
    return voice if voice in _OPENAI_TTS_VOICES else "alloy"


async def transcribe_audio(
    settings: Settings,
    audio_bytes: bytes,
    *,
    filename: str = "speech.m4a",
    language: str | None = None,
) -> str | None:
    if not settings.speech_transcription_enabled:
        return None
    if not audio_bytes or len(audio_bytes) > SPEECH_MAX_AUDIO_BYTES:
        logger.warning(
            "Speech transcription rejected: payload size=%s",
            len(audio_bytes) if audio_bytes else 0,
        )
        return None
    if mock_llm.should_mock_llm(settings):
        return "This is a mock transcription."
    if not settings.openai_api_key:
        return None

    model = (settings.speech_transcription_model or openrouter_slug(_STT_ALIAS)).strip()
    if not speech_gateway.can_transcribe_with(model):
        model = openrouter_slug(_STT_ALIAS)
    text = await speech_gateway.transcribe_via_openai(
        settings,
        audio_bytes,
        filename=filename,
        model=model,
        language=language,
    )
    if text is None:
        return None
    return sanitize_transcript(text, audio_size=len(audio_bytes))


async def synthesize_speech(
    settings: Settings,
    text: str,
    *,
    language: str | None = None,
    model_alias: str | None = None,
    voice: str | None = None,
) -> tuple[bytes, str] | None:
    """Return (audio_bytes, content_type) for OpenAI TTS."""
    if not settings.speech_tts_enabled:
        return None
    plain = " ".join((text or "").split()).strip()
    if not plain:
        return None
    if len(plain) > _MAX_TTS_CHARS:
        plain = plain[:_MAX_TTS_CHARS]
    # Mock chat must not fake TTS when a key is present: a stub MP3 fails
    # playback and the app falls back to on-device speech.
    if mock_llm.should_mock_llm(settings) and not settings.openai_api_key:
        return _MOCK_MP3_BYTES, "audio/mpeg"
    if not settings.openai_api_key:
        return None

    model = resolve_tts_model(settings, alias=model_alias)
    return await speech_gateway.synthesize_via_openai(
        settings,
        plain,
        model=model,
        voice=resolve_tts_voice(settings, model, voice),
        language=language,
    )
