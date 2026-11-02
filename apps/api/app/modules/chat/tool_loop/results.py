"""What a tool call hands back to the turn, read from ``ToolResult.data``.

SymPy results that carry a ``canonical_fence`` are collected so
``validate_math_fences`` can still overwrite/densify geometry and graph fences
the same way the heuristic math_tools path does. A successful ``generate_image``
(or reference photo) is terminal: the stream skips the visible LLM pass and uses
the already-persisted ``[Image: …]`` assistant row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.gateways.mcp.base import ToolResult
from app.gateways.web_search_gateway import WebSearchHit
from app.services.solving import VerifiedMathBlock


@dataclass(frozen=True)
class TerminalImageResult:
    """Successful model-initiated image gen — stream must not create another row."""

    message_id: str
    final_content: str
    resolved_model: str


def _canonical_from_tool_result(result: ToolResult) -> dict[str, Any] | None:
    data = result.data
    if not isinstance(data, dict):
        return None
    fence = data.get("canonical_fence")
    return fence if isinstance(fence, dict) else None


def _canonical_answer_from_tool_result(result: ToolResult) -> str | None:
    data = result.data
    if not isinstance(data, dict):
        return None
    answer = data.get("canonical_answer")
    return answer.strip() if isinstance(answer, str) and answer.strip() else None


def _search_hits_from_tool_result(result: ToolResult) -> list[WebSearchHit]:
    data = result.data
    if not isinstance(data, dict):
        return []
    raw = data.get("hits")
    if not isinstance(raw, list):
        return []
    hits: list[WebSearchHit] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        snippet = str(item.get("snippet") or "")
        if title or url:
            hits.append(WebSearchHit(title=title, url=url, snippet=snippet))
    return hits


def _terminal_image_from_tool_result(result: ToolResult) -> TerminalImageResult | None:
    data = result.data
    if not isinstance(data, dict) or not data.get("terminal"):
        return None
    marker = data.get("image_marker")
    message_id = data.get("assistant_message_id")
    if not isinstance(marker, str) or not marker.startswith("[Image:"):
        return None
    if not isinstance(message_id, str) or not message_id.strip():
        return None
    model = data.get("resolved_model")
    resolved = model if isinstance(model, str) and model.strip() else "image-gen-model"
    return TerminalImageResult(
        message_id=message_id.strip(),
        final_content=marker.strip(),
        resolved_model=resolved,
    )


def _merge_search_hits(existing: list[WebSearchHit], incoming: list[WebSearchHit]) -> None:
    seen = {hit.url.strip().lower() or hit.title.strip().lower() for hit in existing}
    for hit in incoming:
        key = hit.url.strip().lower() or hit.title.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        existing.append(hit)


@dataclass
class ToolResults:
    """What the turn's tool calls produced, merged call by call."""

    # Keyed by type so a geometry fence from one call isn't lost when a later
    # call produces a graph fence.
    canonical_by_type: dict[str, dict[str, Any]] = field(default_factory=dict)
    canonical_answer: str | None = None
    terminal_image: TerminalImageResult | None = None
    search_hits: list[WebSearchHit] = field(default_factory=list)

    def merge(
        self, result: ToolResult | None, *, fence: dict[str, Any] | None, answer: str | None
    ) -> None:
        """Add one call's *result*; *fence* and *answer* are what passed the user-match check."""
        if fence is not None:
            # Merge by type so earlier fences survive later ones.
            fence_type = str(fence.get("type") or "")
            if fence_type:
                self.canonical_by_type[fence_type] = fence
        if answer:
            self.canonical_answer = answer
        image = _terminal_image_from_tool_result(result) if result else None
        if image is not None:
            self.terminal_image = image
        if result is not None:
            _merge_search_hits(self.search_hits, _search_hits_from_tool_result(result))

    def verified_math(self) -> VerifiedMathBlock | None:
        """The verified block for the turn, when a call's fence or answer was the user's problem."""
        all_fences = list(self.canonical_by_type.values())
        if not all_fences and not self.canonical_answer:
            return None
        return VerifiedMathBlock(
            text="",
            canonical_fence=all_fences[0] if all_fences else None,
            canonical_fences=all_fences,
            canonical_answer=self.canonical_answer,
        )
