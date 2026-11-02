"""The model is told Recall searches and shows photos, and the classifier sees the reply."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from app.core.config import Settings
from app.modules.chat.prompt_constants import PHOTO_LOOKUP_HINT
from app.modules.chat.prompt_context_hints import lookup_hints
from app.modules.web_search import WEB_SEARCH_HINT


def _awaited(mock: AsyncMock) -> Any:
    """The last await of *mock*; fails the test when it was never awaited."""
    assert mock.await_args is not None
    return mock.await_args


def _hints(**settings) -> str:
    return "\n".join(lookup_hints(Settings(**settings)))


def test_search_hint_forbids_claiming_no_browsing() -> None:
    assert "never say you can't browse" in WEB_SEARCH_HINT  # safety phrase
    assert WEB_SEARCH_HINT in _hints(web_search_enabled=True)


def test_photo_hint_follows_the_photo_lookup_flag() -> None:
    assert "Never say you can't display, show or send images" in PHOTO_LOOKUP_HINT  # safety phrase
    assert PHOTO_LOOKUP_HINT in _hints(image_search_enabled=True)
    assert PHOTO_LOOKUP_HINT not in _hints(image_search_enabled=False)
