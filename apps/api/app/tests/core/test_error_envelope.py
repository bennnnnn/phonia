"""An HTTPException and a failed validation answer the same body as a DomainError.

They sent ``{"detail": "..."}`` and FastAPI's error list, so the phone read ``code:
null`` for them and could not word them in its language. Now every refusal is
``{"detail": {"code", "message", ...}}``, with its status and headers kept.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.domain_errors import register_domain_error_handler


class _Body(BaseModel):
    size_bytes: int = Field(gt=0, le=10)


def _app() -> TestClient:
    app = FastAPI()
    register_domain_error_handler(app)

    @app.get("/raise/{status_code}")
    async def raise_status(status_code: int, detail: str | None = None) -> None:
        headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
        if status_code == 429:
            headers = {"Retry-After": "7"}
        raise HTTPException(status_code=status_code, detail=detail, headers=headers)

    @app.get("/coded")
    async def coded() -> None:
        raise HTTPException(status_code=403, detail={"code": "not_in_plan", "message": "Pro"})

    @app.post("/validate")
    async def validate(body: _Body) -> dict[str, int]:
        return {"size": body.size_bytes}

    return TestClient(app)


@pytest.mark.parametrize(
    ("status_code", "detail", "code", "message"),
    [
        (404, "Memory not found", "not_found", "Memory not found"),
        (400, "Invalid URL", "invalid", "Invalid URL"),
        (401, "User not found", "unauthorized", "User not found"),
        (413, "Audio payload too large", "too_large", "Audio payload too large"),
        (429, "Slow down", "rate_limited", "Slow down"),
        (404, None, "not_found", "Not Found"),
        # A codeless gateway failure read as Phonia unavailable on the phone; it still does.
        (502, "Could not transcribe audio", "unavailable", "Could not transcribe audio"),
        (503, "Not configured", "unavailable", "Not configured"),
        (418, "Teapot", "refused", "Teapot"),
    ],
)
def test_http_exception_answers_the_refusal_body(
    status_code: int, detail: str | None, code: str, message: str
) -> None:
    params = {"detail": detail} if detail is not None else {}
    response = _app().get(f"/raise/{status_code}", params=params)
    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code, "message": message}}


@pytest.mark.parametrize(
    ("status_code", "header", "value"),
    [(401, "www-authenticate", "Bearer"), (429, "retry-after", "7")],
)
def test_http_exception_keeps_its_headers(status_code: int, header: str, value: str) -> None:
    response = _app().get(f"/raise/{status_code}", params={"detail": "x"})
    assert response.headers[header] == value


def test_http_exception_that_names_a_code_keeps_it() -> None:
    response = _app().get("/coded")
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "not_in_plan", "message": "Pro"}}


def test_a_status_without_a_body_stays_without_one() -> None:
    response = _app().get("/raise/304")
    assert response.status_code == 304
    assert response.content == b""


def test_unknown_route_and_method_answer_the_refusal_body() -> None:
    client = _app()
    missing = client.get("/nowhere")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "not_found"
    wrong = client.delete("/coded")
    assert wrong.status_code == 405
    assert wrong.json()["detail"]["code"] == "method_not_allowed"
    assert "allow" in wrong.headers


def test_validation_failure_names_a_code_and_keeps_fastapis_errors() -> None:
    response = _app().post("/validate", json={"size_bytes": 11})
    assert response.status_code == 422
    detail: dict[str, Any] = response.json()["detail"]
    assert detail["code"] == "invalid"
    assert "less than or equal to 10" in detail["message"]
    assert [error["loc"] for error in detail["errors"]] == [["body", "size_bytes"]]


def test_the_app_registers_the_handlers() -> None:
    from app.main import create_app

    response = TestClient(create_app()).get("/no-such-route")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
