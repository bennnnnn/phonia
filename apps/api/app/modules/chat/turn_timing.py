"""Time-to-first-token and phase timing for chat streams."""

from __future__ import annotations

import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)


class TurnTimingTracker:
    """Monotonic timing for a single chat stream turn (logging only)."""

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._phases_ms: dict[str, float] = {}
        self._prompt_ready_ms: float | None = None
        self._first_token_ms: float | None = None

    def _elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0

    def mark_phase(self, phase: str) -> None:
        self._phases_ms[phase] = self._elapsed_ms()

    def mark_prompt_ready(self) -> None:
        self._prompt_ready_ms = self._elapsed_ms()

    def mark_first_token(self) -> None:
        if self._first_token_ms is None:
            self._first_token_ms = self._elapsed_ms()

    def milestones(self) -> dict[str, float | None]:
        """When the prompt was ready and the first token streamed (the turn's trace)."""
        prompt_ready, first_token = self._prompt_ready_ms, self._first_token_ms
        return {
            "prep_ms": round(prompt_ready, 1) if prompt_ready is not None else None,
            "first_token_ms": round(first_token, 1) if first_token is not None else None,
        }

    def log_summary(
        self,
        *,
        user_id: UUID,
        chat_id: UUID,
        model: str,
        lightweight: bool = False,
        content_chars: int = 0,
    ) -> None:
        prompt_ready = (
            round(self._prompt_ready_ms, 1) if self._prompt_ready_ms is not None else None
        )
        first_token = round(self._first_token_ms, 1) if self._first_token_ms is not None else None
        # This includes any tool-loop work between prompt assembly and the
        # visible stream, so do not label it "provider latency". For non-tool
        # turns it is the closest existing server-side measure of provider TTFT.
        post_prompt_first_token = (
            round(max(0.0, self._first_token_ms - self._prompt_ready_ms), 1)
            if self._first_token_ms is not None and self._prompt_ready_ms is not None
            else None
        )
        gateway_start = self._phases_ms.get("gateway_request_start")
        gateway_to_first_token = (
            round(max(0.0, self._first_token_ms - gateway_start), 1)
            if self._first_token_ms is not None and gateway_start is not None
            else None
        )
        logger.info(
            "chat_stream_timing user_id=%s chat_id=%s model=%s lightweight=%s "
            "content_chars=%s prompt_ready_ms=%s first_token_ms=%s "
            "post_prompt_first_token_ms=%s gateway_to_first_token_ms=%s phases_ms=%s",
            user_id,
            chat_id,
            model,
            lightweight,
            content_chars,
            prompt_ready,
            first_token,
            post_prompt_first_token,
            gateway_to_first_token,
            {phase: round(ms, 1) for phase, ms in self._phases_ms.items()},
        )
