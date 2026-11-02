"""Reference-photo lookup — Tavily image search (server-side only).

Separate from ``web_search_gateway`` (text results) and ``image_gateway``
(AI generation). Returns real, source-linked photo URLs for "what does X
look like" asks; the caller (``services.image_search``) mirrors the bytes
into Recall's own storage via ``safe_fetch`` before ever showing a URL to
a client, so no arbitrary third-party URL is ever rendered on mobile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import Settings
from app.gateways.http_client import get_pooled_client
from app.gateways.mock_llm import should_mock_search

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_SECONDS = 12.0


@dataclass(frozen=True)
class ImageSearchHit:
    image_url: str
    description: str
    source_url: str
    source_title: str


def mock_image_results(query: str, *, max_results: int) -> list[ImageSearchHit]:
    return [
        ImageSearchHit(
            image_url="https://example.com/mock-reference-photo.png",
            description=f"Mock reference photo for: {query[:80]}",
            source_url="https://example.com/mock-search",
            source_title="Mock image search (set TAVILY_API_KEY for live results)",
        )
    ][:max_results]


def _top_result_source(data: dict[str, object]) -> tuple[str, str]:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return "", ""
    first = results[0]
    if not isinstance(first, dict):
        return "", ""
    return (
        str(first.get("url") or "").strip(),
        str(first.get("title") or "").strip(),
    )


# Stock libraries serve watermarked previews: "a cute cartoon skeleton" showed one with
# "shutterstock.com · 2649692539" across it. Their sites and image CDNs are skipped.
_STOCK_HOSTS = (
    "shutterstock.com", "gettyimages.com", "gettyimages.co.uk", "istockphoto.com",
    "alamy.com", "dreamstime.com", "depositphotos.com", "123rf.com", "ftcdn.net",
    "stock.adobe.com", "vectorstock.com", "canstockphoto.com", "bigstockphoto.com",
    "pond5.com", "agefotostock.com", "stockfresh.com", "featurepics.com",
)  # fmt: skip


def _is_stock_preview(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == stock or host.endswith(f".{stock}") for stock in _STOCK_HOSTS)


def _hit_from_image_item(
    item: object, *, source_url: str, source_title: str
) -> ImageSearchHit | None:
    if isinstance(item, str):
        url, description = item.strip(), ""
    elif isinstance(item, dict):
        url = str(item.get("url") or "").strip()
        description = str(item.get("description") or "").strip()
    else:
        return None
    # https-only: Tavily can surface http image URLs from older pages, and
    # the server-side mirror fetch (safe_fetch) only trusts https sources.
    if not url.lower().startswith("https://"):
        return None
    if _is_stock_preview(url):
        return None
    return ImageSearchHit(
        image_url=url,
        description=description[:300],
        source_url=source_url,
        source_title=source_title,
    )


async def search_images(
    settings: Settings,
    query: str,
    *,
    max_results: int = 3,
) -> list[ImageSearchHit]:
    """Real, source-linked photo URLs for *query* via Tavily's include_images.

    Never raises — provider/network failures return an empty list so the
    caller can fall back to a normal chat answer instead of erroring.
    """
    cleaned = query.strip()
    if not cleaned:
        return []
    limit = max(1, min(max_results, 10))

    if not settings.image_search_enabled:
        return []
    if should_mock_search(settings):
        return mock_image_results(cleaned, max_results=limit)
    if not settings.tavily_api_key.strip():
        return []

    payload = {
        "api_key": settings.tavily_api_key,
        "query": cleaned,
        "search_depth": "basic",
        # A handful of text results is enough to attribute the first image
        # hit's source page; the images themselves come from the top-level
        # `images` list, not per-result `images` arrays.
        "max_results": 3,
        "include_answer": False,
        "include_images": True,
        "include_image_descriptions": True,
    }
    try:
        client = get_pooled_client(DEFAULT_TIMEOUT_SECONDS)
        response = await client.post(TAVILY_SEARCH_URL, json=payload)
        response.raise_for_status()
        data = response.json()
    except Exception:
        # Do not log the query — it can contain private user content (CodeQL
        # py/clear-text-logging-sensitive-data).
        logger.exception("Tavily image search failed")
        return []

    if not isinstance(data, dict):
        return []
    source_url, source_title = _top_result_source(data)
    hits: list[ImageSearchHit] = []
    for item in data.get("images") or []:
        hit = _hit_from_image_item(item, source_url=source_url, source_title=source_title)
        if hit is not None:
            hits.append(hit)
        if len(hits) >= limit:
            break
    return hits
