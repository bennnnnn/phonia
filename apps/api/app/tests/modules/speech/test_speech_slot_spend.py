"""Dictation and read-aloud keep the day's slot once the provider was asked.

A 502 after the audio was sent, or a client that hung up mid-call, gave the slot back
while the provider may have billed the call, so the daily cap never bound such a
client. A failure before the call (the flag off, no key) still refunds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.modules.speech import service as speech_service
from app.tests.api_support import api_user, app_with_user

_ROUTES = {
    "transcribe": ("transcribe_audio", "speech"),
    "tts": ("synthesize_speech", "tts"),
}


def _post(client: TestClient, route: str) -> Any:
    headers = {"Authorization": "Bearer tok"}
    if route == "transcribe":
        files = {"file": ("speech.m4a", b"fake-audio", "audio/m4a")}
        return client.post("/speech/transcribe", headers=headers, files=files)
    return client.post("/speech/tts", headers=headers, json={"text": "hello"})


def _provider(asked: bool, outcome: str) -> Callable[..., Any]:
    """A service call that asks the provider (``on_call``) or refuses before it, then
    ends as ``outcome``: ``none`` (nothing usable, a 502) or ``cancel``."""

    async def call(*_args: Any, on_call: Callable[[], None] | None = None, **_kw: Any) -> None:
        if asked and on_call is not None:
            on_call()
        if outcome == "cancel":
            raise asyncio.CancelledError()
        return None

    return call


@pytest.mark.parametrize("route", list(_ROUTES))
@pytest.mark.parametrize("outcome", ["none", "cancel"])
@pytest.mark.parametrize("asked", [True, False])
def test_a_failed_clip_keeps_its_slot_only_once_the_provider_was_asked(
    quota_clock, route: str, outcome: str, asked: bool
) -> None:
    service_fn, prefix = _ROUTES[route]
    user = api_user(plan="plus")
    client = TestClient(app_with_user(user))
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.api.get_redis_client", return_value=redis),
        patch(f"app.modules.speech.api.speech_service.{service_fn}", _provider(asked, outcome)),
    ):
        if outcome == "cancel":
            with pytest.raises((asyncio.CancelledError, RuntimeError)):
                _post(client, route)
        else:
            assert _post(client, route).status_code == 502
        slot = asyncio.run(redis.get(f"{prefix}:{user.id}:2026-10-16"))
    assert slot == ("1" if asked else "0")


@pytest.mark.parametrize(
    "settings, asked",
    [
        ({"openai_api_key": "k", "mock_llm_enabled": False}, True),
        ({"mock_llm_enabled": True}, True),
        ({"openai_api_key": "", "mock_llm_enabled": False}, False),
        ({"speech_transcription_enabled": False}, False),
    ],
)
async def test_transcribe_audio_says_it_asks_the_provider_only_when_it_does(
    settings: dict[str, Any], asked: bool
) -> None:
    order: list[str] = []

    async def gateway(*_args: Any, **_kwargs: Any) -> str:
        order.append("provider")
        return "hello"

    with patch.object(speech_service.speech_gateway, "transcribe_via_openai", gateway):
        await speech_service.transcribe_audio(
            Settings(**settings), b"audio", on_call=lambda: order.append("on_call")
        )
    gateway_called = asked and not settings.get("mock_llm_enabled")
    assert order == (["on_call"] if asked else []) + (["provider"] if gateway_called else [])


@pytest.mark.parametrize(
    "settings, text, asked",
    [
        ({"openai_api_key": "k"}, "hello", True),
        ({"openai_api_key": "", "mock_llm_enabled": True}, "hello", True),
        ({"openai_api_key": "", "mock_llm_enabled": False}, "hello", False),
        ({"openai_api_key": "k"}, "   ", False),
    ],
)
async def test_synthesize_speech_says_it_asks_the_provider_only_when_it_does(
    settings: dict[str, Any], text: str, asked: bool
) -> None:
    order: list[str] = []

    async def gateway(*_args: Any, **_kwargs: Any) -> tuple[bytes, str]:
        order.append("provider")
        return b"mp3", "audio/mpeg"

    with patch.object(speech_service.speech_gateway, "synthesize_via_openai", gateway):
        await speech_service.synthesize_speech(
            Settings(**settings), text, on_call=lambda: order.append("on_call")
        )
    gateway_called = asked and bool(settings.get("openai_api_key"))
    assert order == (["on_call"] if asked else []) + (["provider"] if gateway_called else [])
