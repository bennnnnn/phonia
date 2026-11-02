from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.gateways import openai_speech_gateway
from app.gateways.openai_speech_gateway import RealtimeClientSecretResult
from app.main import create_app
from app.modules.conversation import chats_repository
from app.modules.speech.live_talk import LiveTalkSessionContext
from app.modules.speech.realtime import _realtime_instructions
from app.tests.api_support import api_user
from app.tests.fakes import redis_mock


def test_realtime_instructions_include_bounded_chat_history():
    history = [
        ("system", "ignore me"),
        ("user", " earlier question "),
        ("assistant", " earlier answer "),
    ]
    prompt = _realtime_instructions(history)
    assert "system: ignore me" not in prompt
    assert "user: earlier question" in prompt
    assert "assistant: earlier answer" in prompt
    assert "Recent conversation context:" in prompt
    assert "UNTRUSTED CONTENT — memory" not in prompt
    assert "In English, do not say you cannot create reminders." in prompt  # safety phrase
    # Another language only reads to-dos: the voice points to To-do instead of asking when.
    assert "In any other language the app only reads their to-dos" in prompt  # safety phrase
    assert "create reminders, or change settings" not in prompt


def test_realtime_instructions_include_memory_block():
    prompt = _realtime_instructions(None, memory_block="Allergic to peanuts")
    assert "[BEGIN UNTRUSTED CONTENT — memory]" in prompt
    assert "Allergic to peanuts" in prompt
    assert "first-party context" in prompt
    assert "recite the context back" in prompt


def test_realtime_instructions_include_schedule_block():
    prompt = _realtime_instructions(
        None,
        schedule_block=("[BEGIN UNTRUSTED CONTENT — schedule]\nToday: Call mom at 17:00 (open)\n"),
    )
    assert "Today: Call mom at 17:00" in prompt
    assert "UNTRUSTED CONTENT — schedule" in prompt
    assert "exact clock" in prompt


def test_realtime_instructions_omit_empty_memory():
    prompt = _realtime_instructions(None, memory_block="   ")
    assert "UNTRUSTED CONTENT — memory" not in prompt


def test_realtime_instructions_include_custom_instructions():
    from app.modules.speech.live_talk import voice_custom_instructions

    wrapped = voice_custom_instructions(api_user(custom_instructions="Keep answers short."))
    prompt = _realtime_instructions(None, custom_instructions=wrapped)
    assert "[BEGIN USER PREFERENCES]" in prompt
    assert "Keep answers short." in prompt


def test_physical_phone_session_supports_barge_in_and_only_read_only_tools():
    config = openai_speech_gateway.realtime_session_config(
        Settings(), "Recall", barge_in=True, tools_enabled=True
    )
    assert config["audio"]["input"]["turn_detection"]["interrupt_response"] is True
    assert {tool["name"] for tool in config["tools"]} == {"memory_lookup", "web_search"}


@pytest.mark.parametrize("voice, expected", [(None, "marin"), ("cedar", "cedar")])
def test_session_speaks_in_the_chosen_voice(voice, expected):
    config = openai_speech_gateway.realtime_session_config(Settings(), "Recall", voice=voice)
    assert config["audio"]["output"] == {"voice": expected}


@pytest.mark.asyncio
async def test_realtime_client_secret_binds_session_config_and_retries_connects():
    response = MagicMock()
    response.status_code = 200
    response.text = '{"value":"ek_test","expires_at":123}'
    response.raise_for_status = MagicMock()
    response.json.return_value = {"value": "ek_test", "expires_at": 123}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    settings = Settings(
        openai_api_key="sk-test",
        speech_realtime_voice_enabled=True,
        openai_realtime_model="gpt-realtime-2.1",
    )

    with patch(
        "app.gateways.openai_speech_gateway.get_pooled_client", return_value=client
    ) as pooled:
        result = await openai_speech_gateway.create_realtime_client_secret(
            settings,
            instructions="be concise",
            safety_identifier="user-hash",
        )

    assert result == RealtimeClientSecretResult(value="ek_test", expires_at=123)
    pooled.assert_called_once_with(10.0, connect_retries=2)
    call = client.post.call_args
    assert call.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert call.kwargs["headers"]["OpenAI-Safety-Identifier"] == "user-hash"
    session = call.kwargs["json"]["session"]
    assert session["model"] == "gpt-realtime-2.1"
    assert session["output_modalities"] == ["audio"]
    assert "include" not in session
    assert session["audio"]["input"]["noise_reduction"] == {"type": "near_field"}
    assert session["audio"]["input"]["turn_detection"] == {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
        "create_response": False,
        "interrupt_response": False,
    }
    transcription = session["audio"]["input"]["transcription"]
    assert transcription["model"] == "gpt-live-transcribe"
    assert "Do not invent speech from silence" in transcription["prompt"]


def _realtime_app(user, settings: Settings):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: settings
    return app


@contextmanager
def _session_mint_patches(
    *,
    mint: AsyncMock,
    memory_block: str = "",
    schedule_block: str = "",
):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=fake_redis),
        patch("app.modules.speech.api.get_redis_client", return_value=fake_redis),
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_session_context",
            AsyncMock(return_value=LiveTalkSessionContext(None, memory_block, schedule_block)),
        ),
        patch(
            "app.modules.speech.realtime.openai_speech_gateway.create_realtime_client_secret",
            mint,
        ),
    ):
        yield fake_redis


def test_persist_requires_issued_realtime_session():
    user = api_user(plan="pro")
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
    )
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = TestClient(_realtime_app(user, settings))
    with patch("app.modules.speech.realtime.get_redis_client", return_value=fake_redis):
        r = client.post(
            "/speech/live/persist",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(uuid4()),
                "call_id": "not-a-real-session",
                "user_text": "hello",
                "assistant_text": "hi",
            },
        )
    assert r.status_code == 403


def test_persist_ignores_assistant_only_phantom_turn():
    user = api_user(plan="pro")
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
    )
    client = TestClient(_realtime_app(user, settings))
    with patch("app.modules.speech.realtime.get_redis_client") as redis_client:
        r = client.post(
            "/speech/live/persist",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(uuid4()),
                "call_id": "phantom-session",
                "user_text": "",
                "assistant_text": "Hi there. How can I help?",
            },
        )
    assert r.status_code == 204
    redis_client.assert_not_called()


def test_voice_sources_persist_in_the_canonical_chat_fence():
    import json

    user = api_user(plan="pro")
    client = TestClient(_realtime_app(user, Settings()))
    sources = [{"title": "Official score", "url": "https://example.com/score"}]
    persist = AsyncMock(return_value=(None, None))
    chat_id = uuid4()
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.speech.realtime.live_talk_service.realtime_session_bound_chat_id",
            AsyncMock(return_value=chat_id),
        ),
        patch("app.modules.speech.realtime._take_persist_slot_or_raise", AsyncMock()),
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_history",
            AsyncMock(return_value=([], False)),
        ),
        patch(
            "app.modules.speech.live_talk_tools.search_sources_for_turn",
            AsyncMock(return_value=sources),
        ),
        patch("app.modules.speech.realtime.live_talk_service.persist_live_talk_turn", persist),
    ):
        response = client.post(
            "/speech/live/persist",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(chat_id),
                "call_id": "issued-session",
                "turn_id": "utterance-1",
                "user_text": "Who won?",
                "assistant_text": "Team A won.",
            },
        )
    assert response.status_code == 204
    assert persist.await_args.kwargs["assistant_text"] == (
        "Team A won.\n\n```sources\n" + json.dumps(sources) + "\n```"
    )


@pytest.mark.parametrize("plan", ["free", "plus"])
def test_persist_stops_when_the_plan_no_longer_has_live_talk(plan):
    """Pro ended mid-call: the very next turn is refused, not saved."""
    user = api_user(plan=plan)
    settings = Settings(speech_live_talk_enabled=True, speech_realtime_voice_enabled=True)
    chat_id = uuid4()
    persist = AsyncMock(return_value=(None, None))
    client = TestClient(_realtime_app(user, settings))
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.speech.realtime.quota_service.global_spend_exceeded",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.modules.speech.realtime.live_talk_service.realtime_session_bound_chat_id",
            AsyncMock(return_value=chat_id),
        ),
        patch("app.modules.speech.realtime.live_talk_service.persist_live_talk_turn", persist),
    ):
        response = client.post(
            "/speech/live/persist",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(chat_id),
                "call_id": "issued-session",
                "user_text": "hello",
                "assistant_text": "hi",
            },
        )
    assert response.status_code == 403
    persist.assert_not_awaited()


def test_persist_rejects_when_global_spend_cap_is_hit():
    from app.services.quota import VOICE_SPEND_CAP_MESSAGE

    user = api_user(plan="pro")
    settings = Settings(
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
        daily_global_spend_usd=1.0,
    )
    persist = AsyncMock(return_value=(None, None))
    client = TestClient(_realtime_app(user, settings))
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.speech.realtime.quota_service.global_spend_exceeded",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.speech.realtime.live_talk_service.persist_live_talk_turn", persist),
    ):
        response = client.post(
            "/speech/live/persist",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(uuid4()),
                "call_id": "issued-session",
                "user_text": "hello",
                "assistant_text": "hi",
            },
        )
    assert response.status_code == 429
    assert response.json()["detail"]["message"] == VOICE_SPEND_CAP_MESSAGE
    persist.assert_not_awaited()


def test_persist_rejects_chat_id_that_is_not_bound_to_the_session():
    user = api_user(plan="pro")
    client = TestClient(_realtime_app(user, Settings()))
    persist = AsyncMock(return_value=(None, None))
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=AsyncMock()),
        patch(
            "app.modules.speech.realtime.live_talk_service.realtime_session_bound_chat_id",
            AsyncMock(return_value=uuid4()),
        ),
        patch("app.modules.speech.realtime.live_talk_service.persist_live_talk_turn", persist),
    ):
        response = client.post(
            "/speech/live/persist",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(uuid4()),
                "call_id": "issued-session",
                "user_text": "hello",
                "assistant_text": "hi",
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "live_talk_session_ended"
    persist.assert_not_awaited()


def _minutes_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "openai_api_key": "sk-test",
        "speech_live_talk_enabled": True,
        "speech_realtime_voice_enabled": True,
        "speech_rate_limit_per_minute": 0,
        "monthly_live_talk_minutes_pro": 60,
        "live_talk_max_session_seconds": 900,
        "live_talk_min_session_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("plan", ["free", "plus"])
def test_realtime_session_mint_is_refused_without_live_talk_in_the_plan(plan):
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(api_user(plan=plan), _minutes_settings()))
    with _session_mint_patches(mint=mint) as fake_redis:
        r = client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
        assert r.status_code == 403
        assert not mint.await_count
        assert fake_redis is not None


def test_realtime_session_mint_reserves_a_capped_session_from_the_month():
    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    with _session_mint_patches(mint=mint) as fake_redis:
        r = client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
        assert r.status_code == 200
        assert r.json()["max_duration_seconds"] == 900
        status = client.get("/speech/live", headers={"Authorization": "Bearer tok"}).json()
    assert status["limit"] == 60
    assert status["remaining"] == 45
    assert status["remaining_seconds"] == 3600 - 900
    assert status["entitled"] is True
    assert fake_redis is not None


def test_realtime_session_mint_gets_only_what_is_left():
    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    with _session_mint_patches(mint=mint) as fake_redis:
        import asyncio

        from app.services import quota as quota_service

        key = f"livetalk_sec:{user.id}:{quota_service.utc_month()}"
        asyncio.run(fake_redis.set(key, 3600 - 120))
        r = client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
        assert r.status_code == 200
        assert r.json()["max_duration_seconds"] == 120


def test_realtime_session_mint_refused_below_the_minimum_session():
    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    with _session_mint_patches(mint=mint) as fake_redis:
        import asyncio

        from app.services import quota as quota_service

        key = f"livetalk_sec:{user.id}:{quota_service.utc_month()}"
        asyncio.run(fake_redis.set(key, 3600 - 30))
        r = client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
        assert r.status_code == 429
        assert r.json()["detail"]["message"] == quota_service.LIVE_TALK_MINUTES_USED_MESSAGE
        mint.assert_not_awaited()


def test_realtime_session_mint_failure_gives_the_minutes_back():
    user = api_user(plan="pro")
    mint = AsyncMock(return_value=None)
    client = TestClient(_realtime_app(user, _minutes_settings()))
    with _session_mint_patches(mint=mint):
        r = client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
        assert r.status_code == 502
        status = client.get("/speech/live", headers={"Authorization": "Bearer tok"}).json()
    assert status["remaining_seconds"] == 3600


def test_live_end_settles_to_the_time_used_and_closes_saving():
    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    headers = {"Authorization": "Bearer tok"}
    with _session_mint_patches(mint=mint) as fake_redis:
        import asyncio

        call_id = client.post("/speech/live/session", headers=headers, json={}).json()["call_id"]
        ended = client.post("/speech/live/end", headers=headers, json={"call_id": call_id})
        assert ended.status_code == 200
        # A few seconds at most were used; the rest of the 900 came back.
        assert ended.json()["remaining_seconds"] >= 3600 - 5
        again = client.post("/speech/live/end", headers=headers, json={"call_id": call_id})
        assert again.json()["remaining_seconds"] == ended.json()["remaining_seconds"]
        ttl = asyncio.run(fake_redis.ttl(f"live_talk_rt:{user.id}:{call_id}"))
    # Only the tail for the last turn to save is left of the session.
    assert 0 < ttl <= 60


def test_live_end_cannot_refund_a_session_it_does_not_own():
    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    with _session_mint_patches(mint=mint):
        client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
        r = client.post(
            "/speech/live/end",
            headers={"Authorization": "Bearer tok"},
            json={"call_id": "someone-elses-call"},
        )
    assert r.status_code == 200
    assert r.json()["remaining_seconds"] == 3600 - 900


def test_realtime_session_returns_ephemeral_key_and_recall_session_id():
    user = api_user(plan="pro")
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
        speech_rate_limit_per_minute=0,
    )
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, settings))
    with _session_mint_patches(mint=mint):
        r = client.post(
            "/speech/live/session",
            headers={"Authorization": "Bearer tok"},
            json={},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["client_secret"] == "ek_test"
    assert body["expires_at"] == 123
    assert body["call_id"]
    assert body["model"] == "gpt-realtime-2.1"
    instructions = mint.await_args.kwargs["instructions"]
    assert "UNTRUSTED CONTENT — memory" not in instructions


def test_realtime_session_uses_the_users_voice():
    user = api_user(plan="pro", tts_voice="sage")
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
        speech_rate_limit_per_minute=0,
    )
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, settings))
    with _session_mint_patches(mint=mint):
        r = client.post("/speech/live/session", headers={"Authorization": "Bearer tok"}, json={})
    assert r.status_code == 200
    assert mint.await_args.kwargs["voice"] == "sage"


def test_realtime_session_injects_memory_and_custom_instructions():
    user = api_user(plan="pro", custom_instructions="Keep answers short.")
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
        speech_rate_limit_per_minute=0,
    )
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, settings))
    with _session_mint_patches(mint=mint, memory_block="Lives in Austin"):
        r = client.post(
            "/speech/live/session",
            headers={"Authorization": "Bearer tok"},
            json={},
        )
    assert r.status_code == 200
    instructions = mint.await_args.kwargs["instructions"]
    assert "Lives in Austin" in instructions
    assert "[BEGIN UNTRUSTED CONTENT — memory]" in instructions
    assert "Keep answers short." in instructions
    assert "[BEGIN USER PREFERENCES]" in instructions


def test_realtime_session_injects_schedule_snapshot():
    user = api_user(plan="pro")
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
        speech_rate_limit_per_minute=0,
    )
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, settings))
    with _session_mint_patches(
        mint=mint,
        schedule_block="[BEGIN UNTRUSTED CONTENT — schedule]\nToday: Call mom at 17:00 (open)\n",
    ):
        r = client.post(
            "/speech/live/session",
            headers={"Authorization": "Bearer tok"},
            json={},
        )
    assert r.status_code == 200
    instructions = mint.await_args.kwargs["instructions"]
    assert "Today: Call mom at 17:00" in instructions
    assert "In English, do not say you cannot create reminders." in instructions  # safety phrase


def test_realtime_session_mints_when_memory_load_returns_empty():
    user = api_user(plan="pro")
    user.memory_enabled = False
    settings = Settings(
        openai_api_key="sk-test",
        speech_live_talk_enabled=True,
        speech_realtime_voice_enabled=True,
        speech_rate_limit_per_minute=0,
    )
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, settings))
    with _session_mint_patches(mint=mint, memory_block=""):
        r = client.post(
            "/speech/live/session",
            headers={"Authorization": "Bearer tok"},
            json={},
        )
    assert r.status_code == 200
    instructions = mint.await_args.kwargs["instructions"]
    assert "UNTRUSTED CONTENT — memory" not in instructions


@pytest.mark.parametrize(
    "case,expected",
    [
        ("valid", 200),
        ("wrong_chat", 403),
        ("missing_chat", 404),
        ("free", 403),
        ("plus", 403),
        ("write_tool", 422),
    ],
)
def test_voice_tools_enforce_session_ownership_plan_and_read_only_allowlist(case, expected):
    chat_id = uuid4()
    user = api_user(plan=case if case in {"free", "plus"} else "pro")
    client = TestClient(
        _realtime_app(
            user, Settings(speech_live_talk_enabled=True, speech_realtime_voice_enabled=True)
        )
    )
    redis = redis_mock()
    redis.get.return_value = str(uuid4() if case == "wrong_chat" else chat_id)
    invoke = AsyncMock(return_value={"content": "verified"})
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=redis),
        patch(
            "app.modules.speech.realtime.allow_request_unless_down", AsyncMock(return_value=True)
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None if case == "missing_chat" else MagicMock()),
        ),
        patch("app.modules.speech.live_talk_tools.execute_tool", invoke),
    ):
        response = client.post(
            "/speech/live/tool",
            headers={"Authorization": "Bearer tok"},
            json={
                "chat_id": str(chat_id),
                "call_id": "issued-session",
                "turn_id": "utterance-1",
                "name": "send_email" if case == "write_tool" else "web_search",
                "query": "latest score",
            },
        )
    assert response.status_code == expected
    assert invoke.await_count == int(expected == 200)


def _persist_body(chat_id, call_id: str, n: int) -> dict[str, str]:
    return {
        "chat_id": str(chat_id),
        "call_id": call_id,
        "user_text": f"fake turn {n}",
        "assistant_text": "ok",
    }


@contextmanager
def _persist_patches():
    persist = AsyncMock(return_value=(None, None))
    with (
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_history",
            AsyncMock(return_value=([], False)),
        ),
        patch("app.modules.speech.realtime.live_talk_service.persist_live_talk_turn", persist),
    ):
        yield persist


def test_live_talk_spend_follows_reserved_time_not_posted_turns():
    """A Pro user posting fake turns used to add $0.08 each to everyone's cap."""
    import asyncio

    from app.services import quota as quota_service
    from app.services.quota.spend import live_talk_spend_usd

    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    headers = {"Authorization": "Bearer tok"}
    chat_id = uuid4()
    with _session_mint_patches(mint=mint) as fake_redis, _persist_patches() as persist:
        minted = client.post(
            "/speech/live/session", headers=headers, json={"chat_id": str(chat_id)}
        )
        call_id = minted.json()["call_id"]
        at_mint = asyncio.run(quota_service.get_global_spend_micro_usd(fake_redis))
        for n in range(10):
            saved = client.post(
                "/speech/live/persist", headers=headers, json=_persist_body(chat_id, call_id, n)
            )
            assert saved.status_code == 204
        after_turns = asyncio.run(quota_service.get_global_spend_micro_usd(fake_redis))
        client.post("/speech/live/end", headers=headers, json={"call_id": call_id})
        after_end = asyncio.run(quota_service.get_global_spend_micro_usd(fake_redis))

    assert persist.await_count == 10
    assert at_mint == round(live_talk_spend_usd(900) * 1_000_000)
    assert after_turns == at_mint
    # Only the few seconds the test took stay charged.
    assert after_end <= round(live_talk_spend_usd(5) * 1_000_000)


@pytest.mark.parametrize(
    "month_used_seconds, posts, last_status, last_detail",
    [
        # A 60 s session saves 12 turns, then refuses.
        (3600 - 60, 12, 204, None),
        (3600 - 60, 13, 429, "LIVE_TALK_SAVES_USED_MESSAGE"),
        # A 15 min session has saves to spare; the per-user rate stops a burst.
        (0, 20, 204, None),
        (0, 21, 429, "LIVE_TALK_RATE_LIMIT_MESSAGE"),
    ],
)
def test_live_talk_persist_is_bounded_per_session_and_per_user(
    month_used_seconds: int, posts: int, last_status: int, last_detail: str | None
):
    import asyncio

    from app.services import quota as quota_service

    user = api_user(plan="pro")
    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_test", expires_at=123))
    client = TestClient(_realtime_app(user, _minutes_settings()))
    headers = {"Authorization": "Bearer tok"}
    chat_id = uuid4()
    with _session_mint_patches(mint=mint) as fake_redis, _persist_patches() as persist:
        key = f"livetalk_sec:{user.id}:{quota_service.utc_month()}"
        asyncio.run(fake_redis.set(key, month_used_seconds))
        minted = client.post(
            "/speech/live/session", headers=headers, json={"chat_id": str(chat_id)}
        )
        call_id = minted.json()["call_id"]
        responses = [
            client.post(
                "/speech/live/persist", headers=headers, json=_persist_body(chat_id, call_id, n)
            )
            for n in range(posts)
        ]

    assert all(r.status_code == 204 for r in responses[:-1])
    assert responses[-1].status_code == last_status
    if last_detail is not None:
        assert responses[-1].json()["detail"]["message"] == getattr(quota_service, last_detail)
    assert persist.await_count == posts - int(last_status != 204)
