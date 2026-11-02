"""Tokens a provider reports for a call: prompt, completion and its prompt cache."""

from typing import Any

# Of the prompt tokens: those the provider read from its prompt cache, and those it
# wrote to it (LiteLLM's names for OpenRouter's usage.prompt_tokens_details).
CACHE_DETAILS = (("cached_input", "cached_tokens"), ("cache_write", "cache_write_tokens"))


def apply_usage(usage: dict[str, int] | None, source: Any) -> None:
    """Add a stream chunk's or a whole response's reported tokens onto ``usage``."""
    if usage is None:
        return
    source_usage = getattr(source, "usage", None)
    if not source_usage:
        return
    prompt = getattr(source_usage, "prompt_tokens", None)
    completion = getattr(source_usage, "completion_tokens", None)
    if prompt is not None:
        usage["input"] = usage.get("input", 0) + int(prompt)
    if completion is not None:
        usage["output"] = usage.get("output", 0) + int(completion)
    details = getattr(source_usage, "prompt_tokens_details", None)
    for key, field in CACHE_DETAILS:
        count = getattr(details, field, None)
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            usage[key] = usage.get(key, 0) + count


def merge_attempt_usage(usage: dict[str, int] | None, attempt: dict[str, int]) -> None:
    """Charge the caller for one stream attempt (only an attempt that produced content)."""
    if usage is None:
        return
    usage["input"] = usage.get("input", 0) + attempt.get("input", 0)
    usage["output"] = usage.get("output", 0) + attempt.get("output", 0)
    for key, _field in CACHE_DETAILS:
        if key in attempt:
            usage[key] = usage.get(key, 0) + attempt[key]
