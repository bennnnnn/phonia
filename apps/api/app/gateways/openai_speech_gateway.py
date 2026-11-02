"""Direct OpenAI Realtime boundary for Live Talk.

Composer dictation/read-aloud use speech_gateway; all voice uses OpenAI directly.
No OpenAI key reaches the phone: the server mints a short-lived Realtime client
secret, keeps it, and posts the phone's WebRTC offer with it (``create_realtime_call``),
so it learns the call's id and can end the call itself with the permanent key
(``hangup_realtime_call``). The audio still flows phone <-> OpenAI.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client
from app.models.model_catalog import openrouter_slug

logger = logging.getLogger(__name__)

_OPENAI_REALTIME_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
_OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
_REALTIME_TIMEOUT_SECONDS = 10.0
# A hang-up is one short request; /live/end waits for it, so it may not hang.
_HANGUP_TIMEOUT_SECONDS = 5.0
# OpenAI's call ids (``rtc_…``), read from the answer's Location header; anything else
# is refused before it becomes part of a URL.
_CALL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_REALTIME_CONNECT_RETRIES = 2
_LIVE_TALK_ALIAS = "live-talk-model"
_DEFAULT_REALTIME_VOICE = "marin"
_REALTIME_INPUT_TRANSCRIBE_MODEL = "gpt-live-transcribe"


@dataclass(frozen=True, slots=True)
class RealtimeClientSecretResult:
    value: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class RealtimeCallResult:
    """OpenAI's SDP answer for the phone, and the id of the call it opened."""

    answer_sdp: str
    call_id: str


# ``ended``: OpenAI confirmed the hang-up. ``gone``: it no longer knows the call (404,
# 410), which it opened for us, so the call is not live (the phone's own hang-up got
# there first). ``failed``: anything else, a 400 or 409 included, since neither says the
# call is over: no answer, our key or rate refused, a request it would not take, or its
# own error. The call may still be running, so nothing is refunded and the caller tries
# again.
HangupOutcome = Literal["ended", "gone", "failed"]
_NO_LIVE_CALL = frozenset({404, 410})


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


def _call_id_from_location(location: str) -> str | None:
    """``/v1/realtime/calls/rtc_…`` (or the full URL) -> ``rtc_…``; None if it is not one."""
    candidate = location.strip().rstrip("/").rsplit("/", 1)[-1]
    return candidate if _CALL_ID.fullmatch(candidate) else None


async def create_realtime_call(
    settings: Settings, *, client_secret: str, offer_sdp: str
) -> RealtimeCallResult | None:
    """Post the phone's WebRTC offer with the session's client secret.

    None when OpenAI opened no call we can name: an error status, no Location header,
    or a request that failed. A result may carry an unusable answer; the caller checks
    it and hangs the call up.
    """
    client = get_pooled_client(
        _REALTIME_TIMEOUT_SECONDS,
        connect_retries=_REALTIME_CONNECT_RETRIES,
    )
    try:
        response = await client.post(
            _OPENAI_REALTIME_CALLS_URL,
            headers={
                "Authorization": f"Bearer {client_secret}",
                "Content-Type": "application/sdp",
            },
            content=offer_sdp.encode(),
        )
        if response.status_code >= 400:
            logger.warning(
                "OpenAI Realtime call failed status=%s body=%s",
                response.status_code,
                response.text[:400],
            )
            return None
        call_id = _call_id_from_location(response.headers.get("location", ""))
        if call_id is None:
            logger.warning("OpenAI Realtime call answered without a usable call id")
            return None
        return RealtimeCallResult(answer_sdp=response.text, call_id=call_id)
    except Exception:
        logger.exception("Could not open OpenAI Realtime call")
        return None


async def hangup_realtime_call(settings: Settings, call_id: str) -> HangupOutcome:
    """End a Realtime call (WebRTC or SIP) with the permanent key."""
    key = settings.openai_api_key.strip()
    if not key or not _CALL_ID.fullmatch(call_id):
        return "failed"
    try:
        response = await get_pooled_client(_HANGUP_TIMEOUT_SECONDS).post(
            f"{_OPENAI_REALTIME_CALLS_URL}/{call_id}/hangup",
            headers={"Authorization": f"Bearer {key}"},
        )
    except Exception:
        logger.warning("OpenAI Realtime hang-up failed call=%s", call_id, exc_info=True)
        return "failed"
    if response.status_code < 300:
        return "ended"
    if response.status_code in _NO_LIVE_CALL:
        return "gone"
    logger.warning(
        "OpenAI Realtime hang-up refused call=%s status=%s body=%s",
        call_id,
        response.status_code,
        response.text[:400],
    )
    return "failed"
