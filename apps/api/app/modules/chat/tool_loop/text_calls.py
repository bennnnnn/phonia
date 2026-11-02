"""A tool call the provider wrote into the reply text instead of ``tool_calls``."""

from __future__ import annotations

import json
from typing import Any


def _tool_calls_from_text(
    content: object,
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover a provider-emitted ``!function_call`` as a validated tool call.

    Some OpenAI-compatible providers occasionally serialize the function call
    into assistant text even when ``tools`` were supplied. Only offered tool
    names are accepted here; the normal registry validation still owns the
    arguments before invocation.
    """
    if not isinstance(content, str):
        return []
    marker = "!function_call:"
    start = content.find(marker)
    if start < 0:
        return []
    raw = content[start + len(marker) :].lstrip()
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    name = payload.get("call") or payload.get("name")
    offered = {
        str((tool.get("function") or {}).get("name") or "")
        for tool in tools
        if isinstance(tool, dict)
    }
    if not isinstance(name, str) or name not in offered:
        return []
    arguments = payload.get("arguments", {})
    if isinstance(arguments, dict):
        encoded_arguments = json.dumps(arguments)
    elif isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except (TypeError, ValueError):
            return []
        if not isinstance(parsed_arguments, dict):
            return []
        encoded_arguments = json.dumps(parsed_arguments)
    else:
        return []
    call_id = payload.get("id")
    return [
        {
            "id": call_id if isinstance(call_id, str) and call_id else f"text_{name}",
            "type": "function",
            "function": {"name": name, "arguments": encoded_arguments},
        }
    ]
