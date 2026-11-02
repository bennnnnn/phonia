"""Tool adapter registry."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.gateways.mcp.base import ToolAdapter, ToolContext, ToolResult

_REGISTRY: dict[str, ToolAdapter] = {}


def register(adapter: ToolAdapter) -> None:
    _REGISTRY[adapter.name] = adapter


def get(name: str) -> ToolAdapter | None:
    return _REGISTRY.get(name)


def list_adapters() -> list[ToolAdapter]:
    return list(_REGISTRY.values())


def clear() -> None:
    """Test helper — wipe registered adapters."""
    _REGISTRY.clear()


def build_openai_tools() -> list[dict[str, Any]]:
    """OpenAI/LiteLLM ``tools=`` payloads for registered adapters that expose schemas."""
    tools: list[dict[str, Any]] = []
    for adapter in list_adapters():
        to_tool = getattr(adapter, "to_openai_tool", None)
        if callable(to_tool):
            tools.append(to_tool())
            continue
        schema_cls = getattr(adapter, "input_schema", None)
        if schema_cls is None or not issubclass(schema_cls, BaseModel):
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": adapter.name,
                    "description": adapter.describe(),
                    "parameters": schema_cls.model_json_schema(),
                },
            }
        )
    return tools


async def invoke_validated(
    name: str, raw_args: str | dict[str, Any], ctx: ToolContext
) -> ToolResult | None:
    """Validate tool args with the adapter's Pydantic schema, then run it in *ctx*'s turn."""
    adapter = get(name)
    if adapter is None:
        return ToolResult(name=name or "unknown", content=f"Unknown tool: {name}")

    schema_cls = getattr(adapter, "input_schema", None)
    args: dict[str, Any]
    if isinstance(raw_args, dict):
        payload = raw_args
    else:
        try:
            payload = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            return ToolResult(name=adapter.name, content="Invalid JSON arguments.")

    if schema_cls is not None and issubclass(schema_cls, BaseModel):
        try:
            parsed = schema_cls.model_validate(payload)
            # Preserve omission semantics for partial-update tools. Adapters
            # already provide their own runtime defaults via ``args.get``;
            # materializing every Pydantic default here made an omitted nullable
            # field indistinguishable from an explicit request to clear it.
            args = parsed.model_dump(exclude_unset=True)
        except ValidationError as exc:
            return ToolResult(name=adapter.name, content=f"Invalid arguments: {exc.errors()}")
    else:
        args = payload if isinstance(payload, dict) else {}

    return await adapter.invoke(args, ctx)
