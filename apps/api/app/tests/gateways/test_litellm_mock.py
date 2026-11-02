"""The LiteLLM gateway's mock path, used when no provider key is set."""

from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.modules.chat import titles as chat_titles
from app.modules.memory import llm as memory_llm

# ── litellm gateway (mock path) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_chat_completion_mock():
    from app.gateways import litellm_gateway

    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    tokens = []
    async for t in litellm_gateway.stream_chat_completion(
        settings=settings,
        model_alias="free-chat",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    ):
        tokens.append(t)
    assert len(tokens) > 0
    assert all(isinstance(t, str) for t in tokens)


@pytest.mark.asyncio
async def test_complete_structured_mock_returns_none():
    from app.gateways import litellm_gateway
    from app.modules.memory.schemas import MemorySectionItem

    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    result = await litellm_gateway.complete_structured(
        settings=settings,
        model_alias="title-model",
        messages=[{"role": "user", "content": "hi"}],
        schema=MemorySectionItem,
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_title_mock():
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    title = await chat_titles.generate_title(settings, "Hello", "Hi there")
    assert title == "Greeting"


@pytest.mark.asyncio
async def test_revise_memory_facts_mock():
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    result = await memory_llm.revise_memory_facts(settings, "User likes Python", existing_facts=[])
    assert result is None or hasattr(result, "ops")


@pytest.mark.asyncio
async def test_revise_memory_facts_prompt_user_stated_only():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="test-key")
    captured: dict[str, object] = {}

    async def _capture(**kwargs):
        captured["messages"] = kwargs["messages"]
        return None

    with patch(
        "app.modules.memory.llm.litellm_gateway.complete_structured",
        _capture,
    ):
        await memory_llm.revise_memory_facts(
            settings,
            "User: I work at Acme\nAssistant: Congrats on the new role!",
            existing_facts=[],
        )

    system = captured["messages"][0]["content"]
    assert "Use only what the User lines state or clearly show about the user" in system
    assert "never assistant inferences, suggestions, or restatements" in system
    assert "Each op is ONE fact" in system
    assert "explicitly asks to remember a fact" in system
    assert "explicitly asks to forget a fact" in system
    assert "Rewrite the full section when updating" not in system
    user = captured["messages"][1]["content"]
    assert "[BEGIN UNTRUSTED CONTENT — conversation transcript]" in user
    assert "User: I work at Acme" in user
    assert "[END UNTRUSTED CONTENT — conversation transcript]" in user


@pytest.mark.asyncio
async def test_stream_chat_completion_handles_exception():
    from app.gateways import litellm_gateway
    from app.gateways.litellm_gateway import ModelUnavailableError

    settings = Settings(mock_llm_enabled=False, openrouter_api_key="bad-key")

    async def _fail(**_kwargs):
        raise RuntimeError("network down")

    with patch("app.gateways.litellm_gateway.acompletion", _fail):
        with pytest.raises(ModelUnavailableError) as exc_info:
            async for _t in litellm_gateway.stream_chat_completion(
                settings=settings,
                model_alias="free-chat",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=100,
            ):
                pass
    assert "isn't responding" in exc_info.value.message
