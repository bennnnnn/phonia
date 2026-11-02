"""Tests for app.modules.speech.service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways.speech_gateway import (
    audio_format_from_filename,
    pcm_to_wav,
)
from app.modules.speech.service import (
    SPEECH_MAX_AUDIO_BYTES,
    TTS_FAST_ALIAS,
    TTS_QUALITY_ALIAS,
    normalize_tts_alias,
    resolve_tts_model,
    resolve_tts_voice,
    synthesize_speech,
    transcribe_audio,
)


@pytest.mark.asyncio
async def test_transcribe_returns_mock_when_mock_llm_enabled():
    settings = Settings(
        mock_llm_enabled=True,
        openai_api_key="",
        speech_transcription_enabled=True,
    )
    with patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=True):
        text = await transcribe_audio(settings, b"fake-audio")
    assert text == "This is a mock transcription."


@pytest.mark.asyncio
async def test_transcribe_disabled_returns_none():
    settings = Settings(speech_transcription_enabled=False)
    assert await transcribe_audio(settings, b"fake-audio") is None


@pytest.mark.asyncio
async def test_transcribe_empty_payload_returns_none():
    settings = Settings(mock_llm_enabled=True, speech_transcription_enabled=True)
    assert await transcribe_audio(settings, b"") is None


@pytest.mark.asyncio
async def test_transcribe_rejects_over_shared_byte_cap():
    settings = Settings(mock_llm_enabled=True, speech_transcription_enabled=True)
    assert await transcribe_audio(settings, b"x" * (SPEECH_MAX_AUDIO_BYTES + 1)) is None


def test_audio_format_from_filename_from_filename():
    assert audio_format_from_filename("speech.m4a") == "m4a"
    assert audio_format_from_filename("clip.wav") == "wav"
    assert audio_format_from_filename("clip.mp4") == "m4a"


@pytest.mark.asyncio
async def test_transcribe_openai_multipart_api():
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_transcription_enabled=True,
        speech_transcription_model="openai/gpt-4o-mini-transcribe",
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"text": "hello there"}

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.gateways.speech_gateway.get_pooled_client", return_value=client):
        text = await transcribe_audio(settings, b"audio-bytes", filename="speech.m4a")

    assert text == "hello there"
    call = client.post.call_args
    assert call.args[0] == "https://api.openai.com/v1/audio/transcriptions"
    body = call.kwargs["data"]
    assert body["model"] == "gpt-4o-mini-transcribe"
    assert call.kwargs["files"] == {"file": ("speech.m4a", b"audio-bytes")}
    assert call.kwargs["headers"] == {"Authorization": "Bearer sk-test"}
    assert "language" not in body


@pytest.mark.asyncio
async def test_transcribe_openai_sends_language_hint():
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_transcription_enabled=True,
        speech_transcription_model="openai/gpt-transcribe",
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"text": "hello there"}

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.speech_gateway.get_pooled_client", return_value=client):
        text = await transcribe_audio(
            settings,
            b"audio-bytes",
            filename="speech.m4a",
            language="en-US",
        )

    assert text == "hello there"
    body = client.post.call_args.kwargs["data"]
    assert body["model"] == "gpt-4o-mini-transcribe"
    assert body["language"] == "en"


@pytest.mark.asyncio
async def test_transcribe_drops_watching_hallucination_on_tiny_clip():
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_transcription_enabled=True,
        speech_transcription_model="openai/gpt-transcribe",
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"text": "Thank you for watching!"}

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.speech_gateway.get_pooled_client", return_value=client):
        text = await transcribe_audio(settings, b"tiny", filename="speech.m4a")

    assert text == ""


@pytest.mark.asyncio
async def test_transcribe_openai_empty_text_is_success():
    """Silence is a valid STT result — not a provider failure."""
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_transcription_enabled=True,
        speech_transcription_model="openai/gpt-transcribe",
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = {"text": ""}

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.speech_gateway.get_pooled_client", return_value=client):
        text = await transcribe_audio(settings, b"silence-m4a", filename="speech.m4a")

    assert text == ""


@pytest.mark.asyncio
async def test_transcribe_openai_http_error_is_none():
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_transcription_enabled=True,
    )
    response = MagicMock()
    response.status_code = 502
    response.text = "upstream down"
    response.raise_for_status.side_effect = Exception("502")

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.speech_gateway.get_pooled_client", return_value=client):
        text = await transcribe_audio(settings, b"audio-bytes", filename="speech.m4a")

    assert text is None


@pytest.mark.asyncio
async def test_synthesize_returns_mock_when_mock_llm_enabled():
    settings = Settings(
        mock_llm_enabled=True,
        openai_api_key="",
        speech_tts_enabled=True,
    )
    with patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=True):
        result = await synthesize_speech(settings, "Hello world")
    assert result is not None
    audio, content_type = result
    assert content_type == "audio/mpeg"
    assert len(audio) > 0


@pytest.mark.asyncio
async def test_synthesize_disabled_returns_none():
    settings = Settings(speech_tts_enabled=False)
    assert await synthesize_speech(settings, "Hello") is None


@pytest.mark.asyncio
async def test_synthesize_empty_returns_none():
    settings = Settings(mock_llm_enabled=True, speech_tts_enabled=True)
    with patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=True):
        assert await synthesize_speech(settings, "   ") is None


def test_resolve_tts_model_uses_openai_for_both_aliases_and_stale_overrides():
    settings = Settings(speech_tts_model="openai/gpt-4o-mini-tts")
    assert resolve_tts_model(settings) == "openai/gpt-4o-mini-tts"
    assert resolve_tts_model(Settings(speech_tts_model="")) == ("openai/gpt-4o-mini-tts")
    assert (
        resolve_tts_model(Settings(speech_tts_model="openai/gpt-4o-mini-tts-2025-12-15"))
        == "openai/gpt-4o-mini-tts-2025-12-15"
    )
    assert resolve_tts_model(Settings(), alias=TTS_FAST_ALIAS) == "openai/gpt-4o-mini-tts"
    for stale in ("google/gemini-3.1-flash-tts-preview", "hexgrad/kokoro-82m"):
        assert resolve_tts_model(Settings(speech_tts_model=stale)) == "openai/gpt-4o-mini-tts"
    assert normalize_tts_alias(None) == TTS_QUALITY_ALIAS
    assert normalize_tts_alias("speech-tts-fast-model") == TTS_FAST_ALIAS


def test_resolve_tts_voice_migrates_non_openai_voices():
    for stale in ("Kore", "af_alloy", ""):
        assert (
            resolve_tts_voice(Settings(speech_tts_voice=stale), "openai/gpt-4o-mini-tts") == "alloy"
        )
    assert (
        resolve_tts_voice(Settings(speech_tts_voice="marin"), "openai/gpt-4o-mini-tts") == "marin"
    )


@pytest.mark.parametrize(
    "user_voice, expected",
    [("cedar", "cedar"), (" Coral ", "coral"), (None, "marin"), ("Kore", "marin")],
)
def test_resolve_tts_voice_prefers_the_users_voice(user_voice, expected):
    settings = Settings(speech_tts_voice="marin")
    assert resolve_tts_voice(settings, "openai/gpt-4o-mini-tts", user_voice) == expected


def test_pcm_to_wav_writes_riff_header():
    wav = pcm_to_wav(b"\x00\x00" * 8, sample_rate=24000, channels=1)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_synthesize_openai_omits_language_field():
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_tts_enabled=True,
        speech_tts_model="",
        speech_tts_voice="alloy",
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.content = b"\x00\x00" * 16
    response.text = ""
    response.headers = {"content-type": "audio/pcm;rate=24000;channels=1"}

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.speech_gateway.get_pooled_client", return_value=client),
    ):
        result = await synthesize_speech(settings, "Hello world", language="en-US")

    assert result is not None
    audio, content_type = result
    assert content_type == "audio/wav"
    assert audio[:4] == b"RIFF"
    body = client.post.call_args.kwargs["json"]
    assert client.post.call_args.args[0] == "https://api.openai.com/v1/audio/speech"
    assert client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert body["model"] == "gpt-4o-mini-tts"
    assert body["voice"] == "alloy"
    assert body["response_format"] == "mp3"
    assert "en-US" in body["instructions"]
    assert "language" not in body
    assert "provider" not in body


@pytest.mark.asyncio
async def test_synthesize_legacy_fast_alias_requests_openai_mp3():
    settings = Settings(
        mock_llm_enabled=False,
        openai_api_key="sk-test",
        speech_tts_enabled=True,
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.content = b"ID3kokoro"
    response.text = ""
    response.headers = {"content-type": "audio/mpeg"}
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.speech_gateway.get_pooled_client", return_value=client),
    ):
        result = await synthesize_speech(settings, "Hello", model_alias=TTS_FAST_ALIAS)

    assert result == (b"ID3kokoro", "audio/mpeg")
    body = client.post.call_args.kwargs["json"]
    assert body["model"] == "gpt-4o-mini-tts"
    assert body["voice"] == "alloy"
    assert body["response_format"] == "mp3"


@pytest.mark.asyncio
async def test_synthesize_uses_openai_when_mock_llm_but_key_present():
    settings = Settings(
        mock_llm_enabled=True,
        openai_api_key="sk-test",
        speech_tts_enabled=True,
    )
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.content = b"ID3real-tts"
    response.text = ""
    response.headers = {"content-type": "audio/mpeg"}
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=True),
        patch("app.gateways.speech_gateway.get_pooled_client", return_value=client),
    ):
        result = await synthesize_speech(settings, "Hello")

    assert result == (b"ID3real-tts", "audio/mpeg")
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_voice_never_uses_openrouter_key_as_fallback():
    settings = Settings(mock_llm_enabled=False, openai_api_key="", openrouter_api_key="router-only")
    with (
        patch("app.modules.speech.service.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.speech_gateway.get_pooled_client") as client,
    ):
        assert await transcribe_audio(settings, b"audio") is None
        assert await synthesize_speech(settings, "Hello") is None
        client.assert_not_called()
