"""LLM rolling chat summary (prompt + transport call)."""

from __future__ import annotations

from app.core.config import Settings
from app.gateways import litellm_gateway, mock_llm
from app.models.routing_lanes import ROUTING
from app.modules.chat.context_window import SUMMARY_SYSTEM_PROMPT, cap_summary


async def summarize_conversation(
    settings: Settings,
    prior_summary: str | None,
    messages: list[dict[str, str]],
) -> str | None:
    if mock_llm.should_mock_llm(settings):
        return await mock_llm.mock_summary(prior_summary, messages)

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    parts: list[str] = []
    if prior_summary:
        parts.append(f"Existing summary:\n{prior_summary}")
    parts.append(f"New messages to fold in:\n{transcript}")

    msgs = [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    text = await litellm_gateway.complete_text(
        settings=settings,
        model_alias=ROUTING.background,
        messages=msgs,
        max_tokens=settings.summary_max_tokens,
    )
    return cap_summary(text) if text else None
