"""Tests for app.modules.link_preview.service with mocked HTTP and SSRF validation.

The fetch path now routes through ``app.gateways.safe_fetch.fetch_safely``;
the SSRF-safe DNS pinning + per-hop re-validation is exercised in
``test_safe_fetch.py``. Here we patch ``fetch_safely`` so we can assert the
service calls it with the right URL + UA and parses its response, without
re-testing fetch_safely's internals.
"""

import asyncio
import socket
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.tests.gateways.slow_http_server import dripping_server

_OG_HTML = """<html><head>
<meta property="og:title" content="OG Title">
<meta property="og:description" content="OG Description">
</head></html>"""

_TITLE_HTML = "<html><head><title>Page Title</title></head></html>"

_NO_META_HTML = "<html><head></head><body>Hello</body></html>"


def _mock_response(status=200, text="", headers=None):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.headers = headers or {}
    return m


def _fetch_safely_patch(response):
    """Patch link_preview.fetch_safely to return *response*."""
    return patch(
        "app.modules.link_preview.service.fetch_safely",
        AsyncMock(return_value=response),
    )


@pytest.mark.asyncio
async def test_fetch_link_preview_returns_og_tags():
    """OG meta tags should be parsed as title and description."""
    from app.modules.link_preview.service import fetch_link_preview

    resp = _mock_response(text=_OG_HTML)
    with _fetch_safely_patch(resp) as fetch_mock:
        result = await fetch_link_preview("https://example.com/page")

    assert result["title"] == "OG Title"
    assert result["description"] == "OG Description"
    assert result["domain"] == "example.com"
    fetch_mock.assert_awaited_once()
    # Service must pass the URL through to fetch_safely (SSRF-safe fetch).
    assert fetch_mock.await_args.args[1] == "https://example.com/page"
    # And send the link-preview User-Agent.
    assert fetch_mock.await_args.kwargs["headers"]["User-Agent"].startswith("RecallLinkPreview")
    # Cap the streamed body so a multi-GB upstream cannot OOM the worker.
    assert fetch_mock.await_args.kwargs["max_body_bytes"] == 128 * 1024


@pytest.mark.asyncio
async def test_fetch_link_preview_fallback_to_title():
    """When no OG tags exist, fall back to <title> tag."""
    from app.modules.link_preview.service import fetch_link_preview

    resp = _mock_response(text=_TITLE_HTML)
    with _fetch_safely_patch(resp):
        result = await fetch_link_preview("https://example.com")

    assert result["title"] == "Page Title"
    assert result["description"] is None


@pytest.mark.asyncio
async def test_fetch_link_preview_handles_http_error():
    """HTTP errors should be caught and return nulls, not raised."""
    from app.modules.link_preview.service import fetch_link_preview

    resp = _mock_response(status=500, text="Server Error")
    with _fetch_safely_patch(resp):
        result = await fetch_link_preview("https://example.com/error")

    assert result["title"] is None
    assert result["description"] is None


@pytest.mark.asyncio
async def test_fetch_link_preview_no_meta():
    """Pages with no meta or title tags should return nulls."""
    from app.modules.link_preview.service import fetch_link_preview

    resp = _mock_response(text=_NO_META_HTML)
    with _fetch_safely_patch(resp):
        result = await fetch_link_preview("https://example.com/nometa")

    assert result["title"] is None
    assert result["description"] is None


# ── SSRF validation tests (real address validation) ──


@pytest.mark.asyncio
async def test_validate_external_url_blocks_loopback():
    """127.0.0.1 should be blocked as a loopback address."""
    from app.gateways.safe_fetch import resolve_external_host

    with pytest.raises(ValueError, match="Blocked request"):
        await resolve_external_host("http://127.0.0.1:8080/secret")


@pytest.mark.asyncio
async def test_validate_external_url_blocks_private_range():
    """10.x.x.x should be blocked as a private address."""
    from app.gateways.safe_fetch import resolve_external_host

    with pytest.raises(ValueError, match="Blocked request"):
        await resolve_external_host("http://10.0.0.1/admin")


@pytest.mark.asyncio
async def test_validate_external_url_blocks_link_local():
    """169.254.x.x (AWS/GCP metadata) should be blocked."""
    from app.gateways.safe_fetch import resolve_external_host

    with pytest.raises(ValueError, match="Blocked request"):
        await resolve_external_host("http://169.254.169.254/metadata")


@pytest.mark.asyncio
async def test_validate_external_url_blocks_192_168():
    """192.168.x.x should be blocked."""
    from app.gateways.safe_fetch import resolve_external_host

    with pytest.raises(ValueError, match="Blocked request"):
        await resolve_external_host("http://192.168.1.1:5432")


@pytest.mark.asyncio
async def test_validate_external_url_allows_public():
    """A public IP (e.g., 1.1.1.1) should pass validation."""
    from app.gateways.safe_fetch import resolve_external_host

    # Keep the public-address check real without depending on external DNS.
    with patch.object(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))]),
    ) as resolve:
        await resolve_external_host("https://one.one.one.one/")
    resolve.assert_awaited_once_with("one.one.one.one", None)


@pytest.mark.asyncio
async def test_validate_external_url_no_hostname():
    """A URL with no hostname should raise ValueError."""
    from app.gateways.safe_fetch import resolve_external_host

    with pytest.raises(ValueError, match="URL has no hostname"):
        await resolve_external_host("http:///no-host")


@pytest.mark.asyncio
async def test_pin_url_formats_ipv4_and_ipv6():
    # pin_url lives in safe_fetch now; link_preview delegates to it.
    from app.gateways.safe_fetch import pin_url

    assert pin_url("https://example.com/a?b=1", "1.2.3.4") == "https://1.2.3.4/a?b=1"
    assert pin_url("https://example.com:8443/a", "1.2.3.4") == "https://1.2.3.4:8443/a"
    assert pin_url("https://example.com/a", "2001:db8::1") == "https://[2001:db8::1]/a"


# ── Redirect handling and error path tests ──


@pytest.mark.asyncio
async def test_fetch_link_preview_follows_redirect():
    """Redirects are handled inside fetch_safely; link_preview just parses the final body."""
    from app.modules.link_preview.service import fetch_link_preview

    final_resp = _mock_response(text=_OG_HTML)
    with _fetch_safely_patch(final_resp):
        result = await fetch_link_preview("https://example.com/page")

    assert result["title"] == "OG Title"
    assert result["domain"] == "example.com"


@pytest.mark.asyncio
async def test_fetch_link_preview_blocks_internal_address():
    """When fetch_safely raises ValueError (blocked internal address), return nulls gracefully."""
    from app.modules.link_preview.service import fetch_link_preview

    with patch(
        "app.modules.link_preview.service.fetch_safely",
        AsyncMock(side_effect=ValueError("Blocked request to internal/private address")),
    ):
        result = await fetch_link_preview("http://169.254.169.254/metadata")

    assert result["title"] is None
    assert result["description"] is None
    assert result["domain"] == "169.254.169.254"


@pytest.mark.asyncio
async def test_fetch_link_preview_uses_redis_cache(fake_redis):
    from app.core.config import Settings
    from app.modules.link_preview.service import fetch_link_preview_cached

    settings = Settings(link_preview_cache_ttl=3600)
    resp = _mock_response(text=_OG_HTML)
    user_id = uuid4()
    with _fetch_safely_patch(resp) as fetch_mock:
        first = await fetch_link_preview_cached(
            settings, fake_redis, "https://example.com/page", user_id=user_id
        )
        second = await fetch_link_preview_cached(
            settings, fake_redis, "https://example.com/page", user_id=user_id
        )

    assert first["title"] == "OG Title"
    assert second == first
    # Second call hits the cache; fetch_safely is only called once.
    assert fetch_mock.await_count == 1
    # The fetch slot was given back.
    assert await fake_redis.zcard(f"linkpreview:inflight:{user_id}") == 0


@pytest.mark.asyncio
async def test_fetch_link_preview_passes_an_overall_deadline():
    from app.modules.link_preview.service import fetch_link_preview

    with _fetch_safely_patch(_mock_response(text=_OG_HTML)) as fetch_mock:
        await fetch_link_preview("https://example.com/page")
    assert fetch_mock.await_args.kwargs["deadline_seconds"] == 8.0


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_fetch_link_preview_slow_server_ends_at_the_deadline():
    """A server sending one byte at a time used to hold the request open for minutes."""
    from app.modules.link_preview import service as link_preview

    async with dripping_server(drip_seconds=0.2) as port:
        started = time.monotonic()
        with (
            patch.object(link_preview, "_LINK_PREVIEW_DEADLINE_SECONDS", 0.8),
            patch(
                "app.gateways.safe_fetch.resolve_external_host",
                AsyncMock(return_value=("slow.test", "127.0.0.1")),
            ),
        ):
            result = await link_preview.fetch_link_preview(f"http://slow.test:{port}/page")
        elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert result == {
        "url": f"http://slow.test:{port}/page",
        "title": None,
        "description": None,
        "domain": f"slow.test:{port}",
    }


@pytest.mark.asyncio
async def test_link_preview_caps_fetches_in_flight_per_user(fake_redis):
    """A fourth uncached fetch while three are open is refused; others are not."""
    from app.core.config import Settings
    from app.modules.link_preview.service import LinkPreviewBusyError, fetch_link_preview_cached

    settings = Settings()
    release = asyncio.Event()
    entered: asyncio.Queue[str] = asyncio.Queue()

    async def slow_fetch(url):
        entered.put_nowait(url)
        await release.wait()
        return {"url": url, "title": "T", "description": None, "domain": "example.com"}

    user_id, other_user = uuid4(), uuid4()
    with patch("app.modules.link_preview.service.fetch_link_preview", slow_fetch):
        open_fetches = [
            asyncio.create_task(
                fetch_link_preview_cached(
                    settings, fake_redis, f"https://example.com/{n}", user_id=user_id
                )
            )
            for n in range(3)
        ]
        for _ in range(3):
            await entered.get()
        with pytest.raises(LinkPreviewBusyError):
            await fetch_link_preview_cached(
                settings, fake_redis, "https://example.com/4", user_id=user_id
            )
        other = asyncio.create_task(
            fetch_link_preview_cached(
                settings, fake_redis, "https://example.com/4", user_id=other_user
            )
        )
        await entered.get()
        release.set()
        await asyncio.gather(*open_fetches, other)
        # Slots are given back, so the next fetch runs.
        result = await fetch_link_preview_cached(
            settings, fake_redis, "https://example.com/5", user_id=user_id
        )
    assert result["title"] == "T"


@pytest.mark.asyncio
async def test_link_preview_stale_fetch_slots_age_out(fake_redis):
    """Slots left behind by a crashed fetch do not lock the user out."""
    from app.core.config import Settings
    from app.modules.link_preview.service import fetch_link_preview_cached

    user_id = uuid4()
    key = f"linkpreview:inflight:{user_id}"
    long_ago = time.time() - 120
    await fake_redis.zadd(key, {"a": long_ago, "b": long_ago, "c": long_ago})
    with _fetch_safely_patch(_mock_response(text=_OG_HTML)):
        result = await fetch_link_preview_cached(
            Settings(), fake_redis, "https://example.com/page", user_id=user_id
        )
    assert result["title"] == "OG Title"
    assert await fake_redis.zcard(key) == 0


@pytest.mark.asyncio
async def test_link_preview_slot_fails_closed_when_redis_errors():
    from app.core.config import Settings
    from app.modules.link_preview.service import LinkPreviewBusyError, fetch_link_preview_cached

    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.pipeline = MagicMock(side_effect=ConnectionError("redis down"))
    with (
        _fetch_safely_patch(_mock_response(text=_OG_HTML)) as fetch_mock,
        pytest.raises(LinkPreviewBusyError),
    ):
        await fetch_link_preview_cached(
            Settings(), redis, "https://example.com/page", user_id=uuid4()
        )
    fetch_mock.assert_not_awaited()


def test_link_preview_router_answers_429_when_fetches_are_busy():
    from fastapi.testclient import TestClient

    from app.modules.link_preview.service import LinkPreviewBusyError
    from app.tests.api_support import api_user, app_with_user

    user = api_user()
    with (
        patch("app.modules.link_preview.api.get_redis_client", return_value=MagicMock()),
        patch(
            "app.modules.link_preview.api.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.link_preview.api.fetch_link_preview_cached",
            AsyncMock(side_effect=LinkPreviewBusyError()),
        ),
    ):
        client = TestClient(app_with_user(user))
        r = client.get(
            "/link-preview",
            params={"url": "https://example.com/page"},
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "8"


@pytest.mark.asyncio
async def test_validate_external_url_unresolvable_hostname():
    """An unresolvable hostname should raise ValueError."""
    from app.gateways.safe_fetch import resolve_external_host

    with pytest.raises(ValueError, match="Cannot resolve hostname"):
        await resolve_external_host("http://thishostnamedoesnotexist.invalid/")


def test_link_preview_router_rate_limit_fails_closed():
    from fastapi.testclient import TestClient

    from app.tests.api_support import api_user, app_with_user

    user = api_user()
    with (
        patch("app.modules.link_preview.api.get_redis_client", return_value=MagicMock()),
        patch(
            "app.modules.link_preview.api.allow_request_unless_down",
            AsyncMock(return_value=False),
        ),
    ):
        client = TestClient(app_with_user(user))
        r = client.get(
            "/link-preview",
            params={"url": "https://example.com/page"},
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_fetch_link_preview_reads_a_gzip_page():
    """End to end through the real safe fetch: a gzip page (most sites) gives its title."""
    import gzip

    from app.modules.link_preview.service import fetch_link_preview

    html = b'<html><head><meta property="og:title" content="Gzip Title"></head></html>'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-encoding": "gzip"},
            content=gzip.compress(html),
        )

    def client(_timeout: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)

    with (
        patch("app.modules.link_preview.service.fetch_client", client),
        patch(
            "app.gateways.safe_fetch.resolve_external_host",
            AsyncMock(return_value=("example.org", "93.184.216.34")),
        ),
    ):
        preview = await fetch_link_preview("https://example.org/page")
    assert preview["title"] == "Gzip Title"
