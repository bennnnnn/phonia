"""Tests for gateways: google_auth, mock_llm."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.core.access_tokens import (
    AccessTokenError,
    create_access_token,
    decode_access_token,
)
from app.core.config import Settings
from app.gateways import litellm_gateway, stream_usage, text_completion, think_stripper
from app.gateways.google_auth import GoogleAuthError
from app.gateways.mock_llm import (
    mock_stream,
    mock_title,
    should_mock_llm,
)
from app.gateways.stream_signals import StreamAttempt
from app.modules.chat import titles as chat_titles
from app.modules.memory.offline import offline_memory_facts
from app.modules.todos.schemas import TodoActionItem
from app.tests.modules.chat.chat_test_support import access_for


class _ActionList(BaseModel):
    """A schema with one list field, as the structured-call wrapper expects for bare lists."""

    actions: list[TodoActionItem]


# ── mock_llm ───────────────────────────────────────────────────────────────────


def test_think_stripper_passes_plain_text_through():
    s = think_stripper.ThinkStripper()
    assert s.feed("hello ") + s.feed("world") + s.flush() == "hello world"


def test_think_stripper_removes_closed_think_block():
    s = think_stripper.ThinkStripper()
    open_tag = think_stripper.THINK_OPEN
    close_tag = think_stripper.THINK_CLOSE
    assert (
        s.feed(f"before {open_tag}reasoning here{close_tag} after") + s.flush() == "before  after"
    )


def test_think_stripper_handles_tag_split_across_chunks():
    s = think_stripper.ThinkStripper()
    open_tag = think_stripper.THINK_OPEN
    close_tag = think_stripper.THINK_CLOSE
    split = len(open_tag) // 2
    out = (
        s.feed(f"answer {open_tag[:split]}")
        + s.feed(f"{open_tag[split:]}wrong{close_tag} done")
        + s.flush()
    )
    assert out == "answer  done"


def test_think_stripper_drops_unclosed_block_on_flush():
    s = think_stripper.ThinkStripper()
    open_tag = think_stripper.THINK_OPEN
    assert s.feed(f"visible {open_tag}never closes") + s.flush() == "visible "


def test_think_tags_match_deepseek_fences() -> None:
    """Regression: a source rewrite once renamed the tags so the filter
    never matched R1's inline think fences and CoT leaked into the bubble."""
    assert think_stripper.THINK_OPEN == "<" + "think" + ">"
    assert think_stripper.THINK_CLOSE == "</" + "think" + ">"


def test_think_stripper_strips_long_closed_block() -> None:
    s = think_stripper.ThinkStripper()
    open_tag = think_stripper.THINK_OPEN
    close_tag = think_stripper.THINK_CLOSE
    inner = "the user just wrote 4! " * 400
    assert len(inner) > 4096
    assert s.feed(f"{open_tag}{inner}{close_tag}24") + s.flush() == "24"


@pytest.mark.wall_clock
def test_think_stripper_reads_a_streamed_think_block_once() -> None:
    """Each chunk is searched for the close, not the whole held block again: a 60,000-
    character block streamed a character at a time took 0.7 s of event loop (now ~50 ms)."""
    s = think_stripper.ThinkStripper(lead_hold=think_stripper.STRAY_THINK_LEAD_HOLD)
    text = f"{think_stripper.THINK_OPEN}{'Let me think. ' * 4_600}{think_stripper.THINK_CLOSE}42"
    start = time.perf_counter()
    out = "".join(s.feed(char) for char in text) + s.flush()
    assert time.perf_counter() - start < 0.3
    assert out == "42"


def test_think_stripper_recovers_after_oversized_unclosed_block():
    s = think_stripper.ThinkStripper()
    open_tag = think_stripper.THINK_OPEN
    oversized = "x" * (think_stripper.THINK_MAX_OPEN_BUFFER + 1)
    out = s.feed(f"keep {open_tag}{oversized}") + s.feed(" tail") + s.flush()
    assert out == "keep  tail"


@pytest.mark.asyncio
async def test_stream_chat_once_does_not_forward_reasoning_content() -> None:
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    called: list[str] = []

    class OneChunk:
        def __init__(self) -> None:
            self.done = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.done:
                raise StopAsyncIteration
            self.done = True
            delta = MagicMock()
            delta.content = "24"
            delta.reasoning_content = "The user just wrote 4!, so they want factorial."
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

    async def on_reasoning(chunk: str) -> None:
        called.append(chunk)

    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=OneChunk()),
    ):
        tokens = [
            t
            async for t in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "4!"}],
                max_tokens=10,
                on_reasoning=on_reasoning,
            )
        ]
    assert "".join(tokens) == "24"
    assert called == []


@pytest.mark.asyncio
async def test_stream_chat_completion_wraps_acompletion_failure():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")

    async def fail(**_kwargs):
        raise RuntimeError("network down")

    with patch("app.gateways.litellm_gateway.acompletion", fail):
        with pytest.raises(litellm_gateway.ModelUnavailableError, match="isn't responding"):
            async for _ in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
            ):
                pass


def test_apply_usage_accumulates_onto_existing_totals():
    usage = {"input": 10, "output": 4}
    chunk = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
    )
    stream_usage.apply_usage(usage, chunk)
    assert usage == {"input": 17, "output": 7}


def test_should_mock_llm_true_when_no_key():
    s = Settings(mock_llm_enabled=True, openrouter_api_key="")
    assert should_mock_llm(s) is True


def test_should_mock_llm_false_when_key_present():
    s = Settings(mock_llm_enabled=True, openrouter_api_key="sk-or-real")
    assert should_mock_llm(s) is False


def test_should_mock_llm_false_when_disabled():
    s = Settings(mock_llm_enabled=False, openrouter_api_key="")
    assert should_mock_llm(s) is False


@pytest.mark.asyncio
async def test_mock_stream_yields_words():
    tokens = [t async for t in mock_stream("hello world")]
    assert len(tokens) == 2
    assert "hello" in tokens[0]


@pytest.mark.asyncio
async def test_mock_title_uses_first_words():
    title = await mock_title("I love building AI apps really fast")
    assert title == "I love building AI"


@pytest.mark.asyncio
async def test_mock_title_empty():
    title = await mock_title("")
    assert title is None


@pytest.mark.asyncio
async def test_offline_memory_facts_short_message():
    result = await offline_memory_facts("hi", [])
    assert result is None


# ── complete_structured: bare-list wrapping ───────────────────────────────────


def _fake_completion(content: str):
    """A fake litellm acompletion response whose message.content is `content`."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_complete_structured_wraps_bare_empty_list():
    """Model returning `[]` for a single-list schema should validate to an empty
    result, not raise (regression for the noisy todo-extraction traceback)."""
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    with patch.object(
        litellm_gateway, "acompletion", AsyncMock(return_value=_fake_completion("[]"))
    ):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is not None
    assert isinstance(result, _ActionList)
    assert result.actions == []


@pytest.mark.asyncio
async def test_complete_structured_wraps_bare_list_with_items():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    payload = '[{"action": "add", "topic": "Shopping", "content": "Buy milk"}]'
    with patch.object(
        litellm_gateway, "acompletion", AsyncMock(return_value=_fake_completion(payload))
    ):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is not None
    assert len(result.actions) == 1
    assert result.actions[0].content == "Buy milk"
    assert result.actions[0].topic == "Shopping"


@pytest.mark.asyncio
async def test_complete_structured_accepts_object_form():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    payload = '{"actions": []}'
    with patch.object(
        litellm_gateway, "acompletion", AsyncMock(return_value=_fake_completion(payload))
    ):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is not None
    assert result.actions == []


# ── background LLM fallback on provider outage ───────────────────────────────


@pytest.mark.asyncio
async def test_complete_structured_retries_fallback_on_provider_outage():
    """When the primary model's acompletion raises, retry once against the
    fallback alias so a single-provider outage doesn't silently drop the job."""
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    payload = '{"actions": [{"action": "add", "topic": "T", "content": "C"}]}'
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise RuntimeError("deepseek down")
        return _fake_completion(payload)

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is not None
    assert len(result.actions) == 1
    # First call used the primary model, second used the fallback.
    assert calls[0].endswith("qwen3.7-flash")
    assert calls[1].endswith("claude-haiku-5.5")


@pytest.mark.asyncio
async def test_complete_structured_no_retry_on_bad_output():
    """A successful call that returns unparseable JSON should NOT retry — the
    provider was up, the model just returned bad output, so the fallback won't help."""
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        return _fake_completion("not valid json {{{")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is None
    assert len(calls) == 1  # no fallback attempt


@pytest.mark.asyncio
async def test_complete_structured_can_retry_invalid_output_for_verified_paths():
    """Correctness-sensitive paths can retry malformed structured output."""
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    payload = '{"actions": [{"action": "add", "topic": "T", "content": "C"}]}'
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        return _fake_completion("not valid json {{{" if len(calls) == 1 else payload)

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="title-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
            fallback_on_invalid=True,
        )
    assert result is not None
    assert len(result.actions) == 1
    assert calls[0].endswith("qwen3.7-flash")
    assert calls[1].endswith("claude-haiku-5.5")


@pytest.mark.asyncio
async def test_complete_structured_returns_none_when_both_fail():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        raise RuntimeError("all providers down")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is None
    assert len(calls) == 2  # primary + fallback both tried


@pytest.mark.asyncio
async def test_generate_title_retries_fallback_on_outage():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise RuntimeError("title model down")
        return _fake_completion("My Cool Chat")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        title = await chat_titles.generate_title(settings, "I love building AI apps", "hi there")
    assert title == "My Cool Chat"
    assert len(calls) == 2
    result = await offline_memory_facts(
        "I am working on a Python FastAPI project for my startup",
        [],
    )
    assert result is not None
    assert len(result.ops) == 1
    assert result.ops[0].type == "focus"


@pytest.mark.asyncio
async def test_mock_summary_concatenates_messages():
    from app.gateways.mock_llm import mock_summary

    summary = await mock_summary(
        "Prior context",
        [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}],
    )
    assert "Prior context" in summary
    assert "Hello" in summary


def test_mock_reply_for_messages():
    from app.gateways.mock_llm import mock_reply_for_messages

    reply = mock_reply_for_messages([{"role": "user", "content": "What is 2+2?"}])
    assert isinstance(reply, str)
    assert len(reply) > 0
    assert "```vocab_quiz" not in reply


def test_mock_reply_does_not_emit_vocab_quiz_fences():
    from app.gateways.mock_llm import mock_reply_for_messages

    reply = mock_reply_for_messages(
        [
            {"role": "assistant", "content": "Let's practice."},
            {"role": "user", "content": "B"},
        ]
    )
    assert "```vocab_quiz" not in reply
    assert "Tap another choice" not in reply


# ── access JWT ──────────────────────────────────────────────────────────────────


def test_create_and_decode_token():
    uid = uuid4()
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    token = create_access_token(uid, settings)
    decoded = decode_access_token(token, settings)
    assert decoded == uid


def test_decode_invalid_token_raises():
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    with pytest.raises(AccessTokenError):
        decode_access_token("not-a-jwt", settings)


def test_decode_wrong_secret_raises():
    uid = uuid4()
    s1 = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    s2 = Settings(jwt_secret="different-secret-key-that-is-at-least-32ch!!")
    token = create_access_token(uid, s1)
    with pytest.raises(AccessTokenError):
        decode_access_token(token, s2)


@pytest.mark.asyncio
async def test_verify_google_id_token_requires_email_verified():
    from unittest.mock import patch

    from app.gateways.google_auth import verify_google_id_token

    settings = Settings(google_client_id="test-client")
    payload = {"email_verified": False}
    with patch(
        "app.gateways.google_auth.id_token.verify_oauth2_token",
        return_value=payload,
    ):
        with pytest.raises(GoogleAuthError, match="not verified"):
            await verify_google_id_token("token", settings)


@pytest.mark.asyncio
async def test_verify_google_id_token_runs_on_sign_ins_own_threads():
    """Sync Google cert/HTTP verify runs off the loop, on sign-in's pool (core/blocking.py)."""
    from unittest.mock import patch

    from app.gateways import google_auth
    from app.gateways.google_auth import verify_google_id_token

    settings = Settings(google_client_id="test-client")
    payload = {"email_verified": True, "sub": "g-1", "email": "a@b.c"}
    calls: list[tuple[str, str]] = []
    real_run_blocking = google_auth.run_blocking

    async def spy(kind, func, /, *args, **kwargs):
        calls.append((kind, func.__name__))
        return await real_run_blocking(kind, func, *args, **kwargs)

    with (
        patch(
            "app.gateways.google_auth.id_token.verify_oauth2_token",
            return_value=payload,
        ),
        patch.object(google_auth, "run_blocking", side_effect=spy),
    ):
        out = await verify_google_id_token("token", settings)

    assert out == payload
    assert calls == [("sign_in", "_verify_google_id_token_sync")]


def test_litellm_kwargs_use_openrouter_key():
    from app.gateways import litellm_gateway

    settings = Settings(openrouter_api_key="sk-or")
    route = litellm_gateway.resolve_route("free-chat")
    kwargs = litellm_gateway._litellm_kwargs(settings, route)
    assert kwargs["api_key"] == "sk-or"
    assert "api_base" not in kwargs
    assert route.model == "openrouter/anthropic/claude-haiku-5.5"
    assert "extra_headers" in kwargs


def test_litellm_openrouter_model_prefix():
    from app.models.model_catalog import litellm_openrouter_model

    assert litellm_openrouter_model("deepseek/deepseek-chat") == "openrouter/deepseek/deepseek-chat"
    assert litellm_openrouter_model("openrouter/auto") == "openrouter/openrouter/auto"


# ── deps: get_current_user ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_user_from_valid_token():
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.deps import get_current_user

    uid = uuid4()
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    token = create_access_token(uid, settings)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    fake_user = MagicMock()
    fake_user.id = uid
    session = AsyncMock()
    with (
        patch("app.core.deps.access_tokens.check_access", AsyncMock(return_value=access_for(uid))),
        patch("app.core.deps.users_repo.get_by_id", AsyncMock(return_value=fake_user)),
        patch("app.core.deps.get_settings", return_value=settings),
    ):
        user = await get_current_user(creds, settings, AsyncMock(), session)
    assert user is fake_user


@pytest.mark.asyncio
async def test_get_current_user_returns_its_connection_before_the_route_runs():
    """A cache miss reads the row, then ends that transaction: the request's session stays
    open until the response is sent, and an SSE reply held the connection idle in
    transaction for the whole stream."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from fastapi.security import HTTPAuthorizationCredentials
    from sqlalchemy import text

    from app.core.db import SessionLocal, engine
    from app.core.deps import get_current_user

    uid = uuid4()
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")

    async def read_row(session, user_id):
        await session.execute(text("SELECT 1"))  # the miss's SELECT checks out a connection
        return SimpleNamespace(id=user_id)

    await engine.dispose(close=False)
    try:
        async with SessionLocal() as session:
            with (
                patch(
                    "app.core.deps.access_tokens.check_access",
                    AsyncMock(return_value=access_for(uid)),
                ),
                patch("app.core.deps.users_repo.get_by_id", read_row),
            ):
                user = await get_current_user(creds, settings, AsyncMock(), session)
            assert user.id == uid
            assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose(close=False)


@pytest.mark.asyncio
async def test_get_current_user_not_found_raises_401():
    from unittest.mock import AsyncMock, patch
    from uuid import uuid4

    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.deps import get_current_user

    uid = uuid4()
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")

    with (
        patch("app.core.deps.access_tokens.check_access", AsyncMock(return_value=access_for(uid))),
        patch("app.core.deps.users_repo.get_by_id", AsyncMock(return_value=None)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, settings, AsyncMock(), AsyncMock())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_raises_401():
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.deps import get_current_user

    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")

    with patch(
        "app.core.deps.access_tokens.check_access",
        AsyncMock(side_effect=GoogleAuthError("Invalid token")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, settings, AsyncMock())
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stream_chat_completion_retries_fallback_alias():
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_stream_once(**kwargs):
        alias = kwargs["model_alias"]
        calls.append(alias)
        if alias == "smart-chat":
            raise ModelUnavailableError("down", failed_alias=alias)
        yield "hello"

    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        stream_meta: dict[str, str] = {}
        tokens = [
            t
            async for t in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                fallback_aliases=["free-chat"],
                stream_meta=stream_meta,
            )
        ]
    assert tokens == ["hello"]
    assert calls == ["smart-chat", "free-chat"]
    assert stream_meta["model_alias"] == "free-chat"


@pytest.mark.asyncio
async def test_every_attempted_alias_is_a_health_sample():
    """A failing primary whose fallback answered was never recorded as failing."""
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")

    async def fake_stream_once(**kwargs):
        if kwargs["model_alias"] == "smart-chat":
            raise ModelUnavailableError("down", failed_alias="smart-chat")
        yield "hello"

    attempts: list[StreamAttempt] = []
    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        async for _ in litellm_gateway.stream_chat_completion(
            settings=settings,
            model_alias="smart-chat",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10,
            fallback_aliases=["free-chat"],
            attempts=attempts,
        ):
            pass
    assert [(a.alias, a.failed) for a in attempts] == [("smart-chat", True), ("free-chat", False)]


@pytest.mark.asyncio
async def test_a_stream_that_breaks_after_its_first_token_is_a_failed_sample():
    """A failure after the first token counted as a success."""
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")

    async def fake_stream_once(**_kwargs):
        yield "partial"
        raise ModelUnavailableError("cut", failed_alias="smart-chat")

    attempts: list[StreamAttempt] = []
    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        with pytest.raises(ModelUnavailableError):
            async for _ in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                attempts=attempts,
            ):
                pass
    assert [(a.alias, a.failed) for a in attempts] == [("smart-chat", True)]


@pytest.mark.asyncio
async def test_reasoning_primary_gets_visible_content_deadline_when_fallback_exists():
    """Hidden reasoning must not keep the user waiting before a healthy fallback."""
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        chat_stream_first_content_timeout_seconds=0.05,
    )
    calls: list[tuple[str, float | None]] = []

    async def fake_stream_once(**kwargs):
        alias = kwargs["model_alias"]
        timeout = kwargs["first_content_timeout_seconds"]
        calls.append((alias, timeout))
        if alias == "smart-chat":
            raise ModelUnavailableError("silent", failed_alias=alias)
        yield "ready"

    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        tokens = [
            token
            async for token in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "solve x^2 = 4"}],
                max_tokens=20,
                fallback_aliases=["free-chat"],
            )
        ]

    assert tokens == ["ready"]
    assert calls == [("smart-chat", 0.05), ("free-chat", None)]


class _HiddenReasoningStream:
    """Reasoning chunks every 10 ms; then the answer, after ``answer_after`` of them."""

    def __init__(self, answer_after: int | None = None) -> None:
        self._sent = 0
        self._answer_after = answer_after

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0.01)
        self._sent += 1
        if self._answer_after is not None and self._sent > self._answer_after + 1:
            raise StopAsyncIteration
        delta = MagicMock()
        answering = self._answer_after is not None and self._sent > self._answer_after
        delta.content = "x = 2 or x = -2" if answering else ""
        delta.reasoning_content = "" if answering else "still thinking"
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = None
        chunk = MagicMock()
        chunk.choices = [choice]
        chunk.usage = None
        return chunk


@pytest.mark.asyncio
async def test_stream_chat_once_lets_a_model_streaming_its_reasoning_think():
    """Reasoning that streams ends the first-reply cap; the answer comes after it."""
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_HiddenReasoningStream(answer_after=20)),
    ):
        tokens = [
            token
            async for token in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "solve x^2 = 4"}],
                max_tokens=20,
                first_content_timeout_seconds=0.05,
            )
        ]
    assert "".join(tokens) == "x = 2 or x = -2"


@pytest.mark.asyncio
async def test_stream_chat_once_still_bounds_endless_reasoning_by_the_wall_clock():
    settings = Settings(
        mock_llm_enabled=False, openrouter_api_key="sk-or-test", chat_stream_max_seconds=1
    )
    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=_HiddenReasoningStream()),
    ):
        with pytest.raises(litellm_gateway.ModelUnavailableError) as raised:
            async for _ in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "solve x^2 = 4"}],
                max_tokens=20,
                first_content_timeout_seconds=0.05,
            ):
                pass
    assert raised.value.cause == "timeout"


@pytest.mark.asyncio
async def test_stream_chat_completion_no_fallback_after_tokens_started():
    """Mid-stream ModelUnavailableError must not concatenate partial + fallback."""
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_stream_once(**kwargs):
        alias = kwargs["model_alias"]
        calls.append(alias)
        if alias == "smart-chat":
            yield "partial"
            raise ModelUnavailableError("down mid-stream", failed_alias=alias)
        yield "fallback-full"

    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        tokens: list[str] = []
        with pytest.raises(ModelUnavailableError):
            async for t in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                fallback_aliases=["free-chat"],
            ):
                tokens.append(t)

    assert tokens == ["partial"]
    assert calls == ["smart-chat"]


@pytest.mark.asyncio
async def test_stream_chat_once_records_finish_reason_length():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    stream_meta: dict[str, str] = {}

    class _Delta:
        content = "cut"

    class _Choice:
        delta = _Delta()
        finish_reason = "length"

    class _Chunk:
        choices = [_Choice()]
        usage = None

    async def fake_acompletion(**_kwargs):
        class _Resp:
            async def __aiter__(self):
                yield _Chunk()

        return _Resp()

    with patch.object(litellm_gateway, "acompletion", fake_acompletion):
        tokens = [
            t
            async for t in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=8,
                stream_meta=stream_meta,
            )
        ]
    assert tokens == ["cut"]
    assert stream_meta["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_stream_chat_completion_retries_when_primary_yields_no_tokens():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_stream_once(**kwargs):
        alias = kwargs["model_alias"]
        calls.append(alias)
        if alias == "smart-chat":
            return
            yield  # pragma: no cover — empty async generator
        yield "ok"

    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        stream_meta: dict[str, str] = {}
        tokens = [
            t
            async for t in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                fallback_aliases=["free-chat"],
                stream_meta=stream_meta,
            )
        ]
    assert tokens == ["ok"]
    assert calls == ["smart-chat", "free-chat"]
    assert stream_meta["model_alias"] == "free-chat"


@pytest.mark.asyncio
async def test_stream_chat_completion_retries_when_primary_yields_whitespace_only():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    calls: list[str] = []

    async def fake_stream_once(**kwargs):
        alias = kwargs["model_alias"]
        calls.append(alias)
        if alias == "smart-chat":
            yield "\n"
            yield "  "
            return
        yield "ok"

    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        tokens = [
            t
            async for t in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                fallback_aliases=["free-chat"],
            )
        ]
    assert tokens == ["ok"]
    assert calls == ["smart-chat", "free-chat"]


@pytest.mark.asyncio
async def test_stream_chat_completion_fallback_does_not_keep_discarded_usage():
    """Whitespace-only primary usage must not land on the caller's daily quota."""
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")

    async def fake_stream_once(**kwargs):
        usage = kwargs["usage"]
        alias = kwargs["model_alias"]
        if alias == "smart-chat":
            usage["input"] = usage.get("input", 0) + 100
            usage["output"] = usage.get("output", 0) + 5
            yield "\n"
            return
        usage["input"] = usage.get("input", 0) + 50
        usage["output"] = usage.get("output", 0) + 10
        yield "ok"

    caller_usage = {"input": 7, "output": 1}
    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        tokens = [
            t
            async for t in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                usage=caller_usage,
                fallback_aliases=["free-chat"],
            )
        ]
    assert tokens == ["ok"]
    assert caller_usage == {"input": 57, "output": 11}


@pytest.mark.asyncio
async def test_stream_chat_completion_exhausted_blames_last_alias():
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")

    async def fake_stream_once(**kwargs):
        raise ModelUnavailableError("down", failed_alias=kwargs["model_alias"])
        yield  # pragma: no cover

    stream_meta: dict[str, str] = {}
    with patch.object(litellm_gateway, "_stream_chat_once", fake_stream_once):
        with pytest.raises(ModelUnavailableError) as exc_info:
            async for _ in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                fallback_aliases=["free-chat"],
                stream_meta=stream_meta,
            ):
                pass
    assert exc_info.value.failed_alias == "free-chat"
    assert stream_meta["model_alias"] == "free-chat"


@pytest.mark.asyncio
async def test_stream_chat_completion_raises_when_all_aliases_empty():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")

    async def empty_stream(**_kwargs):
        return
        yield  # pragma: no cover

    with patch.object(litellm_gateway, "_stream_chat_once", empty_stream):
        with pytest.raises(litellm_gateway.ModelUnavailableError, match="isn't responding"):
            async for _ in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="smart-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                fallback_aliases=["free-chat"],
            ):
                pass


@pytest.mark.asyncio
async def test_stream_chat_once_times_out_hung_provider():
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        chat_stream_timeout_seconds=1,
    )

    class HungStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(2)
            raise StopAsyncIteration

    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=HungStream()),
    ):
        with pytest.raises(ModelUnavailableError) as exc_info:
            async for _ in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
            ):
                pass
    assert "isn't responding" in exc_info.value.message


@pytest.mark.asyncio
async def test_stream_chat_once_idle_timeout_allows_long_active_stream():
    """A long reply with steady chunks must not die on total wall-clock time."""
    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        chat_stream_timeout_seconds=1,
    )

    class SlowButActiveStream:
        def __init__(self) -> None:
            self.n = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.n >= 3:
                raise StopAsyncIteration
            self.n += 1
            await asyncio.sleep(0.4)  # total ~1.2s > idle, but gaps < idle
            delta = MagicMock()
            delta.content = f"t{self.n}"
            delta.reasoning_content = None
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=SlowButActiveStream()),
    ):
        tokens = [
            t
            async for t in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
            )
        ]
    assert "".join(tokens) == "t1t2t3"


@pytest.mark.asyncio
async def test_stream_chat_once_wall_clock_stops_slow_drip():
    """A slow drip under the idle timeout must still die on the wall-clock cap."""
    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        chat_stream_timeout_seconds=30,
        chat_stream_max_seconds=1,
    )

    class DripStream:
        def __init__(self) -> None:
            self.n = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.n += 1
            await asyncio.sleep(0.35)
            delta = MagicMock()
            delta.content = "x"
            delta.reasoning_content = None
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunk.usage = None
            return chunk

    with patch(
        "app.gateways.litellm_gateway.acompletion",
        AsyncMock(return_value=DripStream()),
    ):
        with pytest.raises(litellm_gateway.ModelUnavailableError) as exc_info:
            async for _ in litellm_gateway._stream_chat_once(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
            ):
                pass
    assert "isn't responding" in exc_info.value.message


@pytest.mark.asyncio
async def test_acompletion_with_fallback_times_out_hung_provider():
    """A hung background (non-streaming) LLM call must be aborted by the
    background timeout and fall back to the next alias rather than stalling
    the job worker."""
    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        background_llm_timeout_seconds=1,
    )
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        await asyncio.sleep(2)  # exceed the 1s timeout
        return _fake_completion("{}")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await text_completion.acompletion_with_fallback(
            settings,
            "memory-model",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10,
        )
    # Both primary and fallback timed out → None.
    assert result is None
    assert len(calls) == 2
    assert calls[0].endswith("qwen3.7-flash")
    assert calls[1].endswith("claude-haiku-5.5")


@pytest.mark.asyncio
async def test_complete_structured_times_out_hung_provider():
    """complete_structured must abort a hung call via the background timeout
    and return None (after exhausting the fallback) instead of hanging."""
    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        background_llm_timeout_seconds=1,
    )
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        await asyncio.sleep(2)  # exceed the 1s timeout
        return _fake_completion("{}")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
        )
    assert result is None
    # Primary timed out, then fallback also timed out.
    assert len(calls) == 2
    assert calls[0].endswith("qwen3.7-flash")
    assert calls[1].endswith("claude-haiku-5.5")


@pytest.mark.asyncio
async def test_complete_structured_no_fallback_when_disabled():
    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        background_llm_timeout_seconds=1,
        reference_resolve_timeout_seconds=0.05,
    )
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        await asyncio.sleep(1)
        return _fake_completion("{}")

    with patch.object(litellm_gateway, "acompletion", AsyncMock(side_effect=fake_acompletion)):
        result = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_ActionList,
            timeout_seconds=settings.reference_resolve_timeout_seconds,
            allow_fallback=False,
        )
    assert result is None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_embed_text_returns_none_on_timeout():
    from app.gateways import embedding_gateway

    settings = Settings(
        mock_llm_enabled=False,
        openrouter_api_key="sk-or-test",
        background_llm_timeout_seconds=0,
    )

    async def _hang(**_kwargs: object) -> None:
        await asyncio.sleep(30)
        raise AssertionError("aembedding was not cancelled")

    with patch("app.gateways.embedding_gateway.aembedding", _hang):
        result = await embedding_gateway.embed_text(settings, "hello")
    assert result is None


@pytest.mark.asyncio
async def test_embed_text_mock_mode_pads_to_embedding_dim():
    """Mock mode must return a vector padded to EMBEDDING_DIM (1536) so it lands
    in the pgvector `embedding` column — otherwise has_chunks_for_chat /
    search_semantic (which require embedding IS NOT NULL) never fire in
    dev/mock mode and the full RAG pipeline can't be exercised end-to-end."""
    from app.gateways import embedding_gateway
    from app.modules.attachments.chunks_repository import EMBEDDING_DIM

    settings = Settings(mock_llm_enabled=True)
    result = await embedding_gateway.embed_text(settings, "hello")
    assert result is not None
    assert len(result) == EMBEDDING_DIM
