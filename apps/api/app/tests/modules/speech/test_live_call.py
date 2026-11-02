"""The server opens and ends live talk's OpenAI call itself (``speech.live_call``).

``/live/end`` charged the time that had passed and gave the rest back, but nothing
ended the OpenAI call, and the phone held a client secret with no session cap: a
modified client could report the end at once and keep talking on refunded minutes.
Now the secret stays on the server, the phone's offer goes through ``/live/connect``,
the server hangs the call up on ``/live/end`` and when the reservation runs out, and
the unused minutes come back only once OpenAI confirms the call is over.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.core.jobs.delayed import DELAYED_ZSET
from app.gateways import openai_speech_gateway
from app.gateways.openai_speech_gateway import RealtimeCallResult, RealtimeClientSecretResult
from app.main import create_app
from app.modules.speech import live_call
from app.modules.speech.live_talk import LiveTalkSessionContext
from app.tests.api_support import api_user

_HEADERS = {"Authorization": "Bearer tok"}
_OFFER = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111"
_ANSWER = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=answer"
_SETTINGS = Settings(
    openai_api_key="sk-test",
    speech_live_talk_enabled=True,
    speech_realtime_voice_enabled=True,
    speech_rate_limit_per_minute=0,
    monthly_live_talk_minutes_pro=60,
    live_talk_max_session_seconds=900,
    live_talk_min_session_seconds=60,
)


@dataclass
class Live:
    """A Pro user's client over the real routes; OpenAI is recorded fakes."""

    client: TestClient
    redis: Any
    user: Any
    calls: list[dict[str, Any]] = field(default_factory=list)
    hangups: list[str] = field(default_factory=list)
    call: RealtimeCallResult | None = field(
        default_factory=lambda: RealtimeCallResult(answer_sdp=_ANSWER, call_id="rtc_abc123")
    )
    hangup: str = "ended"

    def mint(self) -> str:
        r = self.client.post("/speech/live/session", headers=_HEADERS, json={})
        assert r.status_code == 200, r.text
        assert "client_secret" not in r.json()
        return str(r.json()["call_id"])

    def connect(self, session: str, sdp: str = _OFFER) -> Any:
        return self.client.post(
            "/speech/live/connect", headers=_HEADERS, json={"call_id": session, "sdp": sdp}
        )

    def end(self, session: str) -> Any:
        return self.client.post("/speech/live/end", headers=_HEADERS, json={"call_id": session})

    def remaining(self) -> int:
        return int(self.client.get("/speech/live", headers=_HEADERS).json()["remaining_seconds"])

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def scheduled(self) -> list[tuple[dict[str, Any], float]]:
        """Hang-up jobs waiting in the delayed set: (payload, seconds from now)."""
        now = time.time()
        rows = self.run(self.redis.zrange(DELAYED_ZSET, 0, -1, withscores=True))
        out = []
        for member, score in rows:
            fields = json.loads(member)["fields"]
            assert fields["type"] == live_call.HANGUP_JOB
            out.append((json.loads(fields["payload"]), score - now))
        return out


@pytest.fixture
def live() -> Iterator[Live]:
    user = api_user(plan="pro")
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: _SETTINGS
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    state = Live(client=TestClient(app), redis=redis, user=user)

    async def open_call(_settings: Any, *, client_secret: str, offer_sdp: str) -> Any:
        state.calls.append({"secret": client_secret, "sdp": offer_sdp})
        return state.call

    async def hang_up(_settings: Any, call_id: str) -> str:
        state.hangups.append(call_id)
        return state.hangup

    mint = AsyncMock(return_value=RealtimeClientSecretResult(value="ek_secret", expires_at=123))
    gateway = "app.modules.speech.live_call.openai_speech_gateway"
    with (
        patch("app.modules.speech.realtime.get_redis_client", return_value=redis),
        patch("app.modules.speech.api.get_redis_client", return_value=redis),
        patch("app.modules.speech.live_call.get_redis_client", return_value=redis),
        patch(
            "app.modules.speech.realtime.live_talk_service.load_live_talk_session_context",
            AsyncMock(return_value=LiveTalkSessionContext(None, "", "")),
        ),
        patch(
            "app.modules.speech.realtime.openai_speech_gateway.create_realtime_client_secret",
            mint,
        ),
        patch(f"{gateway}.create_realtime_call", open_call),
        patch(f"{gateway}.hangup_realtime_call", hang_up),
    ):
        yield state


# ── Connect ────────────────────────────────────────────────────────────────


def test_connect_opens_the_call_with_the_kept_secret_and_schedules_its_end(live):
    session = live.mint()

    r = live.connect(session)

    assert r.status_code == 200
    assert r.json() == {"sdp": _ANSWER}
    assert live.calls == [{"secret": "ek_secret", "sdp": _OFFER}]
    # The call is hung up when the 900 reserved seconds run out.
    [(payload, delay)] = live.scheduled()
    assert payload == {"user_id": str(live.user.id), "session_id": session}
    assert 900 <= delay <= 906
    # The secret was taken as it was used: a second connect opens nothing.
    again = live.connect(session)
    assert again.status_code == 403
    assert again.json()["detail"]["code"] == "live_talk_session_ended"
    assert len(live.calls) == 1


def test_a_connect_whose_hang_up_cannot_be_scheduled_ends_the_call_and_is_503(live):
    """``enqueue_later`` swallowed the error: no job would ever have ended the call."""
    session = live.mint()

    with patch(
        "app.modules.speech.live_call.jobs.schedule_job",
        AsyncMock(side_effect=ConnectionError("redis down")),
    ):
        r = live.connect(session)

    assert r.status_code == 503
    assert live.hangups == ["rtc_abc123"]
    assert live.scheduled() == []


def test_the_call_id_outlives_every_retry_of_its_hang_up_job(live):
    """A key that expired mid-retry read as "no call", so the job stopped while the
    call could still run."""
    from app.core.jobs.delayed import MAX_ATTEMPTS, retry_delay_s

    session = live.mint()
    live.connect(session)

    ttl = live.run(live.redis.ttl(f"livetalk_call:{live.user.id}:{session}"))
    [(_payload, hangup_in)] = live.scheduled()
    slowest = sum(retry_delay_s(a, rand=lambda: 1.0) for a in range(2, MAX_ATTEMPTS + 1))
    assert ttl > hangup_in + slowest


@pytest.mark.parametrize("session", ["not-a-session", "someone-elses-session"])
def test_connect_refuses_a_session_this_user_was_not_minted(live, session):
    live.mint()

    r = live.connect(session)

    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "live_talk_session_ended"
    assert live.calls == []


def test_connect_that_opens_no_call_is_upstream_failed_and_the_end_gives_minutes_back(live):
    live.call = None
    session = live.mint()

    r = live.connect(session)

    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "upstream_failed"
    assert live.scheduled() == []
    # No call was opened, so none can run: the end settles at once.
    assert live.end(session).status_code == 200
    assert live.hangups == []
    assert live.remaining() >= 3600 - 5


def test_connect_hangs_up_a_call_whose_answer_is_unusable(live):
    live.call = RealtimeCallResult(answer_sdp="not sdp", call_id="rtc_bad")
    session = live.mint()

    r = live.connect(session)

    assert r.status_code == 502
    assert live.hangups == ["rtc_bad"]


def test_connect_after_the_end_opens_nothing(live):
    session = live.mint()
    live.end(session)

    r = live.connect(session)

    assert r.status_code == 403
    assert live.calls == []


def test_an_end_that_races_the_connect_still_hangs_the_new_call_up(live):
    """/live/end settled while OpenAI was opening the call: the call is ended at once."""
    session = live.mint()
    real_open = live.call

    async def open_call(_settings: Any, *, client_secret: str, offer_sdp: str) -> Any:
        from app.services import quota as quota_service

        await quota_service.settle_live_talk_session(live.redis, live.user.id, session)
        return real_open

    with patch(
        "app.modules.speech.live_call.openai_speech_gateway.create_realtime_call", open_call
    ):
        r = live.connect(session)

    assert r.status_code == 403
    assert live.hangups == ["rtc_abc123"]


# ── End ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("outcome", ["ended", "gone"])
def test_end_hangs_the_call_up_then_charges_only_the_time_used(live, outcome):
    live.hangup = outcome
    session = live.mint()
    live.connect(session)

    r = live.end(session)

    assert r.status_code == 200
    assert live.hangups == ["rtc_abc123"]
    assert r.json()["remaining_seconds"] >= 3600 - 5
    # Idempotent: the call is forgotten once it is over.
    live.end(session)
    assert live.hangups == ["rtc_abc123"]
    ttl = live.run(live.redis.ttl(f"live_talk_rt:{live.user.id}:{session}"))
    assert 0 < ttl <= 60


def test_an_unconfirmed_hang_up_keeps_the_whole_reservation_and_retries(live):
    """The old end refunded on the phone's word alone, while the call could go on."""
    live.hangup = "failed"
    session = live.mint()
    live.connect(session)

    r = live.end(session)

    assert r.status_code == 200
    assert r.json()["remaining_seconds"] == 3600 - 900
    # Saving keeps only its tail; a hang-up job runs now as well as at the reservation's end.
    ttl = live.run(live.redis.ttl(f"live_talk_rt:{live.user.id}:{session}"))
    assert 0 < ttl <= 60
    delays = sorted(delay for _payload, delay in live.scheduled())
    assert delays[0] <= 1 and delays[1] >= 900


# ── The hang-up job ────────────────────────────────────────────────────────


def _job(live: Live, session: str) -> None:
    payload = {"user_id": str(live.user.id), "session_id": session}
    live.run(live_call.handle_hangup_job(_SETTINGS, payload))


def test_the_job_ends_a_call_the_phone_never_reported_and_charges_it_in_full(live):
    session = live.mint()
    live.connect(session)
    # The reservation has run out.
    key = f"livetalk_res:{live.user.id}:{session}"
    reserved, started, month = live.run(live.redis.get(key)).split(":")
    live.run(live.redis.set(key, f"{reserved}:{int(started) - 901_000}:{month}"))

    _job(live, session)

    assert live.hangups == ["rtc_abc123"]
    assert live.remaining() == 3600 - 900
    assert live.run(live.redis.get(key)) is None


def test_the_job_raises_while_the_hang_up_is_unconfirmed_so_the_queue_retries(live):
    live.hangup = "failed"
    session = live.mint()
    live.connect(session)

    with pytest.raises(live_call.LiveCallUnconfirmedError):
        _job(live, session)

    assert live.remaining() == 3600 - 900
    live.hangup = "ended"
    _job(live, session)
    assert live.remaining() >= 3600 - 5


@pytest.mark.parametrize(
    "payload", [{}, {"user_id": "nope", "session_id": "s"}, {"user_id": str(uuid4())}]
)
def test_the_job_ignores_a_payload_it_cannot_read(live, payload):
    live.run(live_call.handle_hangup_job(_SETTINGS, payload))
    assert live.hangups == []


def test_the_job_is_registered():
    from app.background import handlers
    from app.core.jobs import queue

    handlers.register_all()
    assert queue._HANDLERS[live_call.HANGUP_JOB] is live_call.handle_hangup_job


# ── The gateway ────────────────────────────────────────────────────────────


@contextmanager
def _http(response: Any) -> Iterator[MagicMock]:
    client = MagicMock()
    client.post = (
        AsyncMock(return_value=response)
        if response is not None
        else AsyncMock(side_effect=TimeoutError())
    )
    with patch("app.gateways.openai_speech_gateway.get_pooled_client", return_value=client):
        yield client


def _response(status: int, text: str = "", location: str | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = text
    response.headers = {"location": location} if location is not None else {}
    return response


@pytest.mark.parametrize(
    "location, expected",
    [
        ("/v1/realtime/calls/rtc_u1_9c65", "rtc_u1_9c65"),
        ("https://api.openai.com/v1/realtime/calls/rtc_x", "rtc_x"),
        ("/v1/realtime/calls/../hangup?x=1", None),
        (None, None),
    ],
)
async def test_create_realtime_call_posts_the_offer_and_reads_the_call_id(location, expected):
    with _http(_response(201, _ANSWER, location)) as client:
        result = await openai_speech_gateway.create_realtime_call(
            _SETTINGS, client_secret="ek_secret", offer_sdp=_OFFER
        )

    call = client.post.call_args
    assert call.args[0] == "https://api.openai.com/v1/realtime/calls"
    assert call.kwargs["headers"] == {
        "Authorization": "Bearer ek_secret",
        "Content-Type": "application/sdp",
    }
    assert call.kwargs["content"] == _OFFER.encode()
    assert result == (RealtimeCallResult(_ANSWER, expected) if expected else None)


@pytest.mark.parametrize("response", [_response(401, "expired"), None])
async def test_create_realtime_call_is_none_when_openai_opens_nothing(response):
    with _http(response):
        assert (
            await openai_speech_gateway.create_realtime_call(
                _SETTINGS, client_secret="ek", offer_sdp=_OFFER
            )
            is None
        )


@pytest.mark.parametrize(
    "response, expected",
    [
        (_response(200), "ended"),
        (_response(404, "no such call"), "gone"),
        (_response(410, "call ended"), "gone"),
        # Neither says the call is over: no refund until a hang-up is confirmed.
        (_response(400, "bad request"), "failed"),
        (_response(409, "conflict"), "failed"),
        (_response(401, "bad key"), "failed"),
        (_response(429, "slow down"), "failed"),
        (_response(500, "oops"), "failed"),
        (None, "failed"),
    ],
)
async def test_hangup_realtime_call_says_whether_the_call_is_over(response, expected):
    with _http(response) as client:
        outcome = await openai_speech_gateway.hangup_realtime_call(_SETTINGS, "rtc_abc")

    assert outcome == expected
    call = client.post.call_args
    assert call.args[0] == "https://api.openai.com/v1/realtime/calls/rtc_abc/hangup"
    assert call.kwargs["headers"] == {"Authorization": "Bearer sk-test"}


@pytest.mark.parametrize(
    "settings, call_id",
    [(_SETTINGS, "rtc/../other"), (Settings(openai_api_key=""), "rtc_abc")],
)
async def test_hangup_realtime_call_sends_nothing_it_cannot_name(settings, call_id):
    with _http(_response(200)) as client:
        assert await openai_speech_gateway.hangup_realtime_call(settings, call_id) == "failed"
    client.post.assert_not_called()
