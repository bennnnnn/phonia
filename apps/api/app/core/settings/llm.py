"""Model providers and every model call: keys, timeouts, fallbacks, output cap, tool loop."""

from pydantic import BaseModel


class LlmSettings(BaseModel):
    openrouter_api_key: str = ""
    # Direct OpenAI key for all voice: dictation, read-aloud and Live Talk WebRTC.
    openai_api_key: str = ""
    # Model-initiated LiteLLM tools= loop. Ordinary chat streams immediately;
    # the loop runs only when the turn still looks like search / unsolved math /
    # Pro image gen after heuristic inject.
    mcp_tool_loop_enabled: bool = True
    mcp_tool_loop_max_rounds: int = 2
    mcp_tool_loop_timeout_seconds: float = 8.0
    # Tool selection returns calls or a no-tool decision, not the final answer.
    mcp_tool_loop_probe_max_tokens: int = 1024
    mcp_tool_loop_max_calls_per_round: int = 4
    # A tool round's deadline: no call starts after it, and one running at it is cut off.
    mcp_tool_loop_invoke_timeout_seconds: float = 20.0
    # Everything before the reply streams (selection, tool calls, the forced search)
    # shares this budget, so a search or image-host brownout cannot hold "Searching…"
    # for a minute while the turn keeps its lock, quota reservation and socket.
    mcp_tool_loop_total_timeout_seconds: float = 25.0

    # Hard ceiling on a single turn's output tokens. This is a safety backstop
    # against runaway generation and cost, NOT a response-style throttle —
    # brevity is driven by the STYLE_HINTS prompt guidance (short/balanced/
    # detailed). Set high enough that real deliverables (HTML pages, graph
    # JSON, long code) complete instead of truncating mid-fence. The daily
    # token quota (plans.py) is the real per-user cost guardrail. Keep deployed
    # environment overrides aligned with this 8192 default; lower legacy caps
    # can cut advanced derivations off mid-step.
    max_output_tokens: int = 8192
    # Send the chat prompt's stable system message with a cache_control mark to the
    # models that cache only a marked prefix (catalog cache_breakpoints: Claude). Off
    # sends it unmarked; providers that reuse a repeated prefix on their own still do.
    prompt_cache_breakpoints_enabled: bool = True
    # Provider embedding-input char cap (embedding_gateway.embed_text). Was a
    # bare `text[:8000]` inline in the gateway; every other tunable in this
    # codebase lives in Settings, so don't reintroduce an inline magic number
    # here — change this constant instead.
    embedding_input_max_chars: int = 8000
    # embed_many (attachment/chat-history index, memory): inputs per provider
    # request, and requests in flight.
    embedding_batch_size: int = 64
    embedding_concurrency: int = 8

    # Abort a provider stream after this many seconds with no new chunk. A stall
    # mid-reply froze the bubble for 3 min; the phone says "still working" at 20 s.
    # Reasoning chunks count, and the cap below applies. Production's value: no
    # deploy file overrides it (test_config_sources.py).
    chat_stream_timeout_seconds: int = 30
    # Hard cap on one provider stream (seconds). Stops a slow drip from holding
    # the chatprep lock, RAM, and the OpenRouter meter indefinitely.
    chat_stream_max_seconds: int = 600
    # Fail fast when the provider never opens an SSE stream (separate from read
    # timeout), soon enough for the model fallback chain to help. The last model in
    # the chain waits the idle timeout above instead: with no backup, failing at 5 s
    # left a slow-opening reply empty.
    chat_stream_connect_timeout_seconds: int = 5
    # A paid reasoning lane may think silently before its first token. When a
    # fallback exists, an attempt that has sent neither text nor reasoning after
    # this long gives way to it; one streaming its reasoning is left to think
    # (the idle and wall-clock caps above still bound it).
    chat_stream_first_content_timeout_seconds: float = 8.0
    # Fail fast while another model can take over (the last one in the chain
    # always gets the idle timeout above). Auto's everyday lane does not think
    # and shows its first text in about a second: an attempt that has shown
    # nothing (no text, no thinking) after this long gives way to the next.
    chat_stream_first_text_timeout_seconds: float = 3.0
    # A model that always thinks (the free plan's hard and maths lane) streams
    # its reasoning from the start: one that has sent neither reasoning nor
    # text after this long gives way to the next.
    chat_stream_first_thought_timeout_seconds: float = 4.0
    # A model whose breaker opened (services/model_health) is skipped for this
    # long after its last sample; then a turn about to try it claims its probe.
    model_health_cooldown_seconds: int = 30

    # Abort hung background (non-streaming) LLM calls after this many seconds.
    # Covers title generation, memory extraction, todos, summaries — a hung
    # provider would otherwise stall the job worker indefinitely.
    background_llm_timeout_seconds: int = 60
    # Dev placeholder: canned replies when no provider key is set. Production
    # boot refuses it (validate_production_settings).
    mock_llm_enabled: bool = True
