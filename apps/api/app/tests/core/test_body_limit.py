"""Oversized request bodies are refused before a route buffers them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.body_limit import RequestBodyLimitMiddleware
from app.core.config import Settings

_LIMIT = 1024
_UPLOAD_LIMIT = 4096
_SCAN_LIMIT = 2048


class _Body(BaseModel):
    text: str


def _app(read_log: list[int]) -> ASGIApp:
    """Test app behind the cap; ``read_log`` records every body chunk the cap let through."""
    app = FastAPI()

    @app.post("/json")
    async def json_route(body: _Body) -> dict[str, int]:
        return {"chars": len(body.text)}

    @app.post("/raw")
    async def raw_route(request: Request) -> dict[str, int]:
        data = await request.body()
        return {"bytes": len(data)}

    @app.post("/speech/transcribe")
    async def upload_route(request: Request) -> dict[str, int]:
        data = await request.body()
        return {"bytes": len(data)}

    @app.post("/math/scan/read")
    async def scan_route(request: Request) -> dict[str, int]:
        data = await request.body()
        return {"bytes": len(data)}

    async def counting_app(scope: Scope, receive: Receive, send: Send) -> None:
        async def counted() -> Message:
            message = await receive()
            if message.get("type") == "http.request":
                read_log.append(len(message.get("body", b"")))
            return message

        await app(scope, counted, send)

    return RequestBodyLimitMiddleware(
        counting_app,
        upload_paths=(r"/speech/transcribe",),
        scan_paths=(r"/(math|physics|chemistry)/scan/read",),
    )


_PATH_LIMITS = {"/speech/transcribe": _UPLOAD_LIMIT, "/math/scan/read": _SCAN_LIMIT}


def _settings() -> Settings:
    return Settings(
        max_request_body_bytes=_LIMIT,
        max_upload_request_body_bytes=_UPLOAD_LIMIT,
        max_scan_request_body_bytes=_SCAN_LIMIT,
    )


async def _chunks(total: int, step: int = 256) -> AsyncIterator[bytes]:
    sent = 0
    while sent < total:
        piece = min(step, total - sent)
        sent += piece
        yield b"a" * piece


def _json_body(size: int) -> bytes:
    filler = "a" * max(0, size - len('{"text": ""}'))
    return ('{"text": "' + filler + '"}').encode()


@pytest.mark.parametrize(
    "path, size, chunked, expected_status",
    [
        ("/json", _LIMIT - 100, False, 200),
        ("/json", _LIMIT + 1, False, 413),
        ("/raw", _LIMIT + 1, True, 413),
        ("/raw", _LIMIT * 50, True, 413),
        ("/speech/transcribe", _LIMIT * 3, False, 200),
        ("/speech/transcribe", _UPLOAD_LIMIT + 1, False, 413),
        ("/speech/transcribe", _UPLOAD_LIMIT + 1, True, 413),
        # A scan read-back gets its own cap, below the upload cap.
        ("/math/scan/read", _SCAN_LIMIT - 10, False, 200),
        ("/math/scan/read", _SCAN_LIMIT + 1, False, 413),
        ("/math/scan/read", _SCAN_LIMIT + 1, True, 413),
    ],
)
async def test_body_limit_rejects_oversized_bodies(
    path: str, size: int, chunked: bool, expected_status: int
) -> None:
    read_log: list[int] = []
    app = _app(read_log)
    content = _chunks(size) if chunked else (_json_body(size) if path == "/json" else b"a" * size)
    with patch("app.core.body_limit.get_settings", return_value=_settings()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.post(
                path, content=content, headers={"content-type": "application/json"}
            )
    assert response.status_code == expected_status
    if expected_status == 413:
        limit = _PATH_LIMITS.get(path, _LIMIT)
        # Never buffers more than one chunk past the cap.
        assert sum(read_log) <= limit + 256
        assert response.json() == {
            "detail": {"code": "too_large", "message": "Request body too large"}
        }


async def test_body_limit_declared_length_rejected_without_reading() -> None:
    read_log: list[int] = []
    app = _app(read_log)
    with patch("app.core.body_limit.get_settings", return_value=_settings()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.post("/raw", content=b"a" * (_LIMIT * 4))
    assert response.status_code == 413
    assert read_log == []
    # The shared refusal shape, as the streamed path answers.
    assert response.json()["detail"]["code"] == "too_large"


async def test_body_limit_zero_disables_cap() -> None:
    read_log: list[int] = []
    app = _app(read_log)
    settings = Settings(max_request_body_bytes=0, max_upload_request_body_bytes=0)
    with patch("app.core.body_limit.get_settings", return_value=settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.post("/raw", content=_chunks(_LIMIT * 10))
    assert response.status_code == 200
    assert response.json() == {"bytes": _LIMIT * 10}


async def test_body_limit_is_mounted_on_the_api() -> None:
    from app.main import create_app

    app = create_app()
    settings = _settings()
    with patch("app.core.body_limit.get_settings", return_value=settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            response = await client.post(
                "/auth/google",
                content=_chunks(_LIMIT * 20),
                headers={"content-type": "application/json"},
            )
            declared = await client.post("/auth/google", content=b"a" * (_LIMIT * 4))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "too_large"
    assert declared.status_code == 413
    assert declared.json() == response.json()


def test_the_scan_cap_fits_the_largest_scan_and_stays_below_the_upload_cap() -> None:
    from app.main import SCAN_BODY_PATHS, UPLOAD_BODY_PATHS
    from app.models.schemas.scan import SCAN_MAX_REQUEST_BYTES

    settings = Settings()
    assert SCAN_MAX_REQUEST_BYTES <= settings.max_scan_request_body_bytes
    assert settings.max_scan_request_body_bytes < settings.max_upload_request_body_bytes
    assert not any("scan" in pattern for pattern in UPLOAD_BODY_PATHS)
    assert SCAN_BODY_PATHS == (r"/(math|physics|chemistry)/scan/read",)
