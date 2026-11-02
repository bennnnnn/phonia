"""Direct OpenAI dictation and read-aloud HTTP calls (provider boundary)."""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client

logger = logging.getLogger(__name__)

_OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
_OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
_TRANSCRIBE_TIMEOUT = 20.0
_TTS_TIMEOUT = 60.0
_DEFAULT_PCM_RATE = 24000
# The OpenAI audio models this gateway calls. An operator override outside them is not
# used (``speech.service``), so a stale Gemini or Kokoro name never reaches OpenAI.
_TRANSCRIBE_MODELS = frozenset({"gpt-4o-mini-transcribe", "gpt-4o-transcribe"})
_SPEECH_MODEL_FAMILY = "gpt-4o-mini-tts"
_DEFAULT_PCM_CHANNELS = 1
_PCM_SAMPLE_WIDTH = 2

_AUDIO_FORMAT_BY_SUFFIX: dict[str, str] = {
    ".m4a": "m4a",
    ".mp3": "mp3",
    ".mp4": "m4a",
    ".wav": "wav",
    ".webm": "webm",
    ".flac": "flac",
    ".caf": "m4a",
    ".3gp": "m4a",
}


def can_transcribe_with(model: str) -> bool:
    """Whether ``model`` (``openai/`` or bare) is one this gateway transcribes with."""
    return model.removeprefix("openai/") in _TRANSCRIBE_MODELS


def can_speak_with(model: str) -> bool:
    """Whether ``model`` (``openai/`` or bare) is one this gateway reads aloud with."""
    return model.removeprefix("openai/").startswith(_SPEECH_MODEL_FAMILY)


def audio_format_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return _AUDIO_FORMAT_BY_SUFFIX.get(suffix, suffix.lstrip(".") or "m4a")


def pcm_to_wav(
    pcm: bytes,
    *,
    sample_rate: int = _DEFAULT_PCM_RATE,
    channels: int = _DEFAULT_PCM_CHANNELS,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(max(channels, 1))
        wav.setsampwidth(_PCM_SAMPLE_WIDTH)
        wav.setframerate(sample_rate if sample_rate > 0 else _DEFAULT_PCM_RATE)
        wav.writeframes(pcm)
    return buf.getvalue()


def _parse_pcm_params(content_type: str) -> tuple[int, int]:
    rate, channels = _DEFAULT_PCM_RATE, _DEFAULT_PCM_CHANNELS
    for part in content_type.lower().split(";"):
        token = part.strip()
        if token.startswith("rate="):
            digits = token[5:].strip()
            if digits.isdigit():
                rate = int(digits)
        elif token.startswith("channels="):
            digits = token[9:].strip()
            if digits.isdigit():
                channels = int(digits)
    return rate, channels


def _stt_language_code(language: str | None) -> str | None:
    raw = (language or "").strip().lower().replace("_", "-")
    if not raw:
        return None
    primary = raw.split("-", 1)[0]
    if len(primary) == 2 and primary.isalpha():
        return primary
    return None


async def transcribe_via_openai(
    settings: Settings,
    audio_bytes: bytes,
    *,
    filename: str,
    model: str,
    language: str | None = None,
) -> str | None:
    audio_format = audio_format_from_filename(filename)
    payload: dict[str, str] = {
        "model": model.removeprefix("openai/"),
        "response_format": "json",
    }
    lang = _stt_language_code(language)
    if lang:
        payload["language"] = lang
    try:
        client = get_pooled_client(_TRANSCRIBE_TIMEOUT)
        response = await client.post(
            _OPENAI_TRANSCRIBE_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
            },
            data=payload,
            files={"file": (Path(filename).name, audio_bytes)},
        )
        if response.status_code >= 400:
            logger.warning(
                "OpenAI transcription failed model=%s format=%s size=%s status=%s body=%s",
                model,
                audio_format,
                len(audio_bytes),
                response.status_code,
                response.text[:500],
            )
        response.raise_for_status()
        data = response.json()
        text = str(data.get("text") or "").strip()
        if not text:
            logger.info(
                "OpenAI transcription heard no speech model=%s format=%s size=%s",
                model,
                audio_format,
                len(audio_bytes),
            )
        # Empty string is a successful silence result. None is reserved for
        # HTTP/provider failures so the router can 502 only those.
        return text
    except Exception:
        logger.exception(
            "Speech transcription failed model=%s format=%s size=%s",
            model,
            audio_format,
            len(audio_bytes),
        )
        return None


def _tts_request_payload(
    *,
    model: str,
    text: str,
    voice: str,
    response_format: str,
    language: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model.removeprefix("openai/"),
        "input": text,
        "voice": voice,
        "response_format": response_format,
    }
    payload["instructions"] = _openai_tts_instructions(language)
    return payload


def _openai_tts_instructions(language: str | None) -> str:
    base = "Speak clearly and naturally, as a helpful assistant reading a message aloud."
    locale = (language or "").strip()
    if not locale:
        return base
    return f"{base} Use a natural voice appropriate for locale {locale}."


async def synthesize_via_openai(
    settings: Settings,
    text: str,
    *,
    model: str,
    voice: str,
    language: str | None = None,
) -> tuple[bytes, str] | None:
    # Locale is a voice instruction, not an unsupported `language` field.
    response_format = "mp3"
    payload = _tts_request_payload(
        model=model,
        text=text,
        voice=voice,
        response_format=response_format,
        language=language,
    )
    try:
        client = get_pooled_client(_TTS_TIMEOUT)
        response = await client.post(
            _OPENAI_SPEECH_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code >= 400:
            logger.warning(
                "OpenAI TTS failed model=%s status=%s body=%s",
                model,
                response.status_code,
                response.text[:500],
            )
        response.raise_for_status()
        audio = response.content
        if not audio:
            logger.warning("OpenAI TTS returned empty audio model=%s", model)
            return None
        header_type = (response.headers.get("content-type") or "").lower()
        content_type = header_type.split(";")[0].strip()
        looks_pcm = "pcm" in header_type or (
            response_format == "pcm"
            and "mpeg" not in header_type
            and "mp3" not in header_type
            and "wav" not in header_type
        )
        if looks_pcm:
            rate, channels = _parse_pcm_params(header_type)
            return pcm_to_wav(audio, sample_rate=rate, channels=channels), "audio/wav"
        return audio, content_type or "audio/mpeg"
    except Exception:
        logger.exception("Speech TTS failed model=%s chars=%s", model, len(text))
        return None
