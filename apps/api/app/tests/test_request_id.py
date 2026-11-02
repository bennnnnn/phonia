"""Tests for RequestIdMiddleware and CORS allowlist in main.py."""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_access_log_emitted_for_legal_not_health(caplog):
    """Structured access log fires for real routes; Fly probes stay quiet."""
    caplog.set_level(logging.INFO, logger="app.http")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/health")
        privacy = await client.get("/legal/privacy")
    assert privacy.status_code == 200
    records = [r for r in caplog.records if r.name == "app.http"]
    assert records
    assert all(getattr(r, "http_path", "") != "/health" for r in records)
    logged = next(r for r in records if r.http_path == "/legal/privacy")
    assert logged.http_method == "GET"
    assert logged.http_status == 200
    assert isinstance(logged.duration_ms, float)


@pytest.mark.asyncio
async def test_request_id_echoed_from_client():
    """A valid client-supplied X-Request-ID is echoed on the response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "abc-123_def"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "abc-123_def"


@pytest.mark.asyncio
async def test_request_id_generated_when_missing():
    """When the client doesn't send X-Request-ID, the server generates one."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    rid = response.headers["X-Request-ID"]
    assert rid
    # Generated IDs are UUID4 hex strings (32 chars) — definitely not empty.
    assert len(rid) >= 8


@pytest.mark.asyncio
async def test_request_id_regenerated_when_invalid():
    """A client-supplied X-Request-ID that doesn't match the allowlist is replaced.

    This is the security fix: without validation, a client could inject
    newlines/control chars (log injection) or absurdly long values (log
    truncation / DoS). Only ``^[A-Za-z0-9_-]{1,64}$`` is accepted.
    """
    transport = ASGITransport(app=app)
    cases = [
        "has spaces",
        "with\nnewline",
        "with;semicolon",
        "x" * 65,  # too long
        "",
        "has.dot",
    ]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for bad in cases:
            response = await client.get("/health", headers={"X-Request-ID": bad})
            rid = response.headers["X-Request-ID"]
            assert rid != bad
            # Generated replacement must itself be valid.
            assert rid
            assert rid.isalnum() or all(c in "-_" or c.isalnum() for c in rid)


@pytest.mark.asyncio
async def test_cors_allow_methods_explicit():
    """CORS preflight echoes only the explicit allowlisted methods, not wildcard."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    # CORS middleware responds to preflight with 200 even if the route is GET-only.
    allow_methods = response.headers.get("access-control-allow-methods", "")
    # Must NOT be a wildcard.
    assert "*" not in allow_methods
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        assert method in allow_methods


@pytest.mark.asyncio
async def test_cors_allow_headers_explicit():
    """CORS preflight echoes only the explicit allowlisted headers, not wildcard."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, x-request-id, x-csrf-token",
            },
        )
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "*" not in allow_headers
    for header in ("authorization", "content-type", "x-request-id", "x-csrf-token"):
        assert header in allow_headers.lower()
