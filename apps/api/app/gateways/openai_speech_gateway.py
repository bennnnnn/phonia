"""Direct OpenAI Realtime boundary for Live Talk.

Composer dictation/read-aloud use speech_gateway; all voice uses OpenAI directly.
The permanent OpenAI API key never leaves the Recall server; mobile receives
only a short-lived Realtime client secret and performs the SDP exchange itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client
from app.models.model_catalog import openrouter_slug

logger = logging.getLogger(__name__)

_OPENAI_REALTIME_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
_REALTIME_TIMEOUT_SECONDS = 10.0
_REALTIME_CONNECT_RETRIES = 2
_LIVE_TALK_ALIAS = "live-talk-model"
_DEFAULT_REALTIME_VOICE = "marin"
_REALTIME_INPUT_TRANSCRIBE_MODEL = "gpt-live-transcribe"


@dataclass(frozen=True, slots=True)
class RealtimeClientSecretResult:
    value: str
    expires_at: int


def realtime_model(settings: Settings) -> str:
    """The operator's override, else the catalog's live-talk model (OpenAI's own name)."""
    override = settings.openai_realtime_model.strip()
    return override or openrouter_slug(_LIVE_TALK_ALIAS).removeprefix("openai/")


def realtime_session_config(
    settings: Settings,
    instructions: str,
    *,
    barge_in: bool = False,
    tools_enabled: bool = False,
    voice: str | None = None,
) -> dict[str, object]:
    config: dict[str, object] = {
        "type": "realtime",
        "model": realtime_model(settings),
        "output_modalities": ["audio"],
        "instructions": instructions,
        "audio": {
            "input": {
                # WebRTC manages playback truncation on interruption. Older
                # clients and the iOS Simulator retain half-duplex behavior.
                "noise_reduction": {"type": "near_field"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "create_response": False,
                    "interrupt_response": barge_in,
                },
                "transcription": {
                    "model": _REALTIME_INPUT_TRANSCRIBE_MODEL,
                    "prompt": (
                        "Transcribe only words actually spoken by the user. "
                        "Do not invent speech from silence, background noise, "
                        "music, or assistant speaker playback."
                    ),
                },
            },
            "output": {"voice": voice or _DEFAULT_REALTIME_VOICE},
        },
    }
    if tools_enabled:
        config["tools"] = [
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "maxLength": 500}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            }
            for name, description in (
                (
                    "memory_lookup",
                    "Look up relevant saved personal preferences or past context when needed. Never dump the user's profile.",
                ),
                (
                    "web_search",
                    "Check live facts such as news, scores and current prices. Not for greetings or ordinary personal advice. Never search private profile details.",
                ),
            )
        ]
    return config


async def create_realtime_client_secret(
    settings: Settings,
    *,
    instructions: str,
    safety_identifier: str,
    barge_in: bool = False,
    tools_enabled: bool = False,
    voice: str | None = None,
) -> RealtimeClientSecretResult | None:
    """Mint a short-lived key that mobile can use for direct WebRTC setup."""
    key = settings.openai_api_key.strip()
    if not key or not settings.speech_realtime_voice_enabled:
        return None

    model = realtime_model(settings)
    client = get_pooled_client(
        _REALTIME_TIMEOUT_SECONDS,
        connect_retries=_REALTIME_CONNECT_RETRIES,
    )
    try:
        response = await client.post(
            _OPENAI_REALTIME_CLIENT_SECRETS_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "OpenAI-Safety-Identifier": safety_identifier[:128],
            },
            json={
                "session": realtime_session_config(
                    settings,
                    instructions,
                    barge_in=barge_in,
                    tools_enabled=tools_enabled,
                    voice=voice,
                )
            },
        )
        if response.status_code >= 400:
            logger.warning(
                "OpenAI Realtime client-secret failed model=%s status=%s body=%s",
                model,
                response.status_code,
                response.text[:800],
            )
        response.raise_for_status()
        payload = response.json()
        value = str(payload.get("value") or "").strip()
        expires_at = int(payload.get("expires_at") or 0)
        if not value:
            logger.warning("OpenAI Realtime client-secret response missing value")
            return None
        return RealtimeClientSecretResult(value=value, expires_at=expires_at)
    except Exception:
        logger.exception("Could not mint OpenAI Realtime client secret")
        return None
