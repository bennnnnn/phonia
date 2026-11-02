"""Title and description for a link card, fetched server-side and cached.

The phone asks only for links the user wrote or the reply's search sources
named; a link the model wrote on its own is a plain card with no fetch, so a
prompt-injected reply cannot make the server request a URL carrying the
user's data (``apps/mobile/components/LinkPreviewCard.tsx``).

Every fetch has an overall deadline (``fetch_safely``), and one user has at
most ``_MAX_IN_FLIGHT_PER_USER`` fetches open at once, so slow upstreams
cannot pile up open requests on the API machine.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from urllib.parse import urlparse
from uuid import UUID

import httpx
from redis.asyncio import Redis

from app.core.config import Settings
from app.gateways.safe_fetch import fetch_client, fetch_safely

logger = logging.getLogger(__name__)

_OG_TAG_RE = re.compile(
    r'<meta\s+(?:[^>]*?\s)?(?:property|name)=["\'](og:[^"\']+|description|twitter:title)["\'](?:\s[^>]*)?\scontent=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)

_USER_AGENT = "RecallLinkPreview/1.0"
# Cap bytes streamed from the upstream — OG/meta tags live near the top; a
# multi-GB body must not be buffered into API memory (rate limit alone is not
# enough — each request can still be huge within the timeout).
_LINK_PREVIEW_MAX_BODY_BYTES = 128 * 1024
_LINK_PREVIEW_MAX_HTML_CHARS = 120_000
# Each read may take this long; the whole fetch (DNS, up to five redirect hops
# and the body) gets _LINK_PREVIEW_DEADLINE_SECONDS in all.
_LINK_PREVIEW_READ_TIMEOUT_SECONDS = 6.0
_LINK_PREVIEW_DEADLINE_SECONDS = 8.0
# A chat shows a few cards at once; more open fetches than this for one user
# is a client looping over URLs. An entry older than the TTL is a fetch that
# can no longer be running (the deadline is far shorter), e.g. after a crash.
_MAX_IN_FLIGHT_PER_USER = 3
_IN_FLIGHT_TTL_SECONDS = 30
_IN_FLIGHT_PREFIX = "linkpreview:inflight:"


class LinkPreviewBusyError(Exception):
    """The user already has the most link-preview fetches open at once."""


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "meta":
            data = {k.lower(): (v or "") for k, v in attrs}
            key = data.get("property") or data.get("name")
            content = data.get("content")
            if key and content:
                self.meta[key.lower()] = content


async def fetch_link_preview(url: str) -> dict[str, str | None]:
    parsed = urlparse(url)
    domain = parsed.netloc or url
    title: str | None = None
    description: str | None = None

    try:
        async with fetch_client(httpx.Timeout(_LINK_PREVIEW_READ_TIMEOUT_SECONDS)) as client:
            # SSRF-safe fetch: DNS pinning + per-hop re-validation of every
            # redirect target, all inside one overall deadline.
            resp = await fetch_safely(
                client,
                url,
                deadline_seconds=_LINK_PREVIEW_DEADLINE_SECONDS,
                headers={"User-Agent": _USER_AGENT},
                max_body_bytes=_LINK_PREVIEW_MAX_BODY_BYTES,
            )
            resp.raise_for_status()
            html = resp.text[:_LINK_PREVIEW_MAX_HTML_CHARS]
    except ValueError:
        # Re-raised from resolve_external_host -- blocked internal address
        logger.debug("Link preview blocked internal address: %s", url)
        return {"url": url, "title": None, "description": None, "domain": domain}
    except TimeoutError:
        logger.info("Link preview passed its %.0fs deadline", _LINK_PREVIEW_DEADLINE_SECONDS)
        return {"url": url, "title": None, "description": None, "domain": domain}
    except httpx.HTTPStatusError as exc:
        # A site that refuses bots (403) or a dead page: expected, not ours to fix.
        logger.info("Link preview of %s got HTTP %s", domain, exc.response.status_code)
        return {"url": url, "title": None, "description": None, "domain": domain}
    except Exception as exc:
        # Ours to look at (a page that could not be decoded hid every preview): the
        # site and the error's kind, never the full URL.
        logger.warning("Link preview fetch failed for %s: %s", domain, type(exc).__name__)
        return {"url": url, "title": None, "description": None, "domain": domain}

    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        logger.debug("Meta parse failed", exc_info=True)

    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title
    description = parser.meta.get("og:description") or parser.meta.get("description")

    if not title:
        m = _TITLE_RE.search(html)
        if m:
            title = m.group(1).strip()

    if not title and not description:
        for match in _OG_TAG_RE.finditer(html):
            key, value = match.group(1).lower(), match.group(2).strip()
            if key in {"og:title", "twitter:title"} and not title:
                title = value
            if key in {"og:description", "description"} and not description:
                description = value

    return {
        "url": url,
        "title": title,
        "description": description,
        "domain": domain,
    }


def _preview_cache_key(url: str) -> str:
    digest = hashlib.sha256(url.strip().lower().encode()).hexdigest()[:32]
    return f"linkpreview:{digest}"


@asynccontextmanager
async def _in_flight_slot(redis: Redis, user_id: UUID) -> AsyncIterator[None]:
    """Hold one of the user's fetch slots, or raise ``LinkPreviewBusyError``.

    A sorted set of open fetches scored by start time: stale entries age out
    on the next request, so a crashed fetch never locks the user out. A Redis
    error denies the fetch, like the rate limit in front of it.
    """
    key = f"{_IN_FLIGHT_PREFIX}{user_id}"
    member = uuid.uuid4().hex
    now = time.time()
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", now - _IN_FLIGHT_TTL_SECONDS)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, _IN_FLIGHT_TTL_SECONDS)
            _, _, open_fetches, _ = await pipe.execute()
    except Exception as exc:
        logger.warning("Link preview slot check failed; denying", exc_info=True)
        raise LinkPreviewBusyError from exc
    try:
        if int(open_fetches) > _MAX_IN_FLIGHT_PER_USER:
            raise LinkPreviewBusyError
        yield
    finally:
        try:
            await redis.zrem(key, member)
        except Exception:
            logger.debug("Link preview slot release failed", exc_info=True)


async def fetch_link_preview_cached(
    settings: Settings, redis: Redis, url: str, *, user_id: UUID
) -> dict[str, str | None]:
    """The cached card, or a fresh fetch inside one of the user's fetch slots."""
    cache_key = _preview_cache_key(url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            payload = json.loads(cached)
            if isinstance(payload, dict):
                return {
                    "url": str(payload.get("url") or url),
                    "title": payload.get("title"),
                    "description": payload.get("description"),
                    "domain": str(payload.get("domain") or urlparse(url).netloc or url),
                }
    except Exception:
        logger.debug("Link preview cache read failed", exc_info=True)

    async with _in_flight_slot(redis, user_id):
        result = await fetch_link_preview(url)
    try:
        await redis.set(
            cache_key,
            json.dumps(result),
            ex=max(60, settings.link_preview_cache_ttl),
        )
    except Exception:
        logger.debug("Link preview cache write failed", exc_info=True)
    return result
