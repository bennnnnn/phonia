"""POST /math/scan/read: the scanner's reading, before anything is solved."""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.main import create_app
from app.models.orm import User
from app.models.schemas.scan import SCAN_MAX_IMAGE_BYTES
from app.modules.math.api import readable_reading
from app.modules.math.ocr import MathOcrResult
from app.modules.math.schemas import MathImageExtract

_IMAGE = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()


def _client(settings: Settings | None = None) -> TestClient:
    user = MagicMock(spec=User)
    user.id = uuid4()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: settings or Settings()
    return TestClient(app)


def _redis(*, spend_exceeded: bool = False, allowed: bool = True) -> Any:
    return (
        patch("app.services.scan_read.get_redis_client", return_value=MagicMock()),
        patch(
            "app.services.scan_read.quota_service.global_spend_exceeded",
            AsyncMock(return_value=spend_exceeded),
        ),
        patch(
            "app.services.scan_read.quota_service.record_global_spend",
            AsyncMock(return_value=0),
        ),
        patch("app.services.scan_read.allow_request_unless_down", AsyncMock(return_value=allowed)),
    )


def _ocr(result: MathOcrResult | Exception) -> Any:
    mock = (
        AsyncMock(side_effect=result)
        if isinstance(result, Exception)
        else AsyncMock(return_value=result)
    )
    return patch("app.modules.math.api.extract_math_from_image", mock)


def _post(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post("/math/scan/read", headers={"Authorization": "Bearer tok"}, json=body)


def test_scan_read_returns_the_reading_without_solving() -> None:
    result = MathOcrResult(
        extract=MathImageExtract(lhs="2*x+3", rhs="7", variables=["x"], found=True),
        display_text="2*x+3 = 7",
        source="mathpix",
        confidence=0.97,
        uncertain=False,
    )
    patches = _redis()
    with patches[0], patches[1], patches[2] as spend, patches[3], _ocr(result) as ocr:
        response = _post(_client(), {"image_base64": _IMAGE, "content_type": "image/png"})
    assert response.status_code == 200
    assert response.json() == {"reading": "2x+3 = 7", "uncertain": False, "source": "mathpix"}
    assert ocr.await_args.kwargs["content_type"] == "image/png"
    spend.assert_awaited_once()


def test_scan_read_with_nothing_legible_is_uncertain() -> None:
    empty = MathOcrResult(
        extract=None, display_text="", source="none", confidence=None, uncertain=True
    )
    patches = _redis()
    with patches[0], patches[1], patches[2], patches[3], _ocr(empty):
        response = _post(_client(), {"image_base64": _IMAGE})
    assert response.json() == {"reading": "", "uncertain": True, "source": "none"}


def test_scan_read_failure_degrades_to_an_empty_reading() -> None:
    patches = _redis()
    with patches[0], patches[1], patches[2] as spend, patches[3], _ocr(RuntimeError("down")):
        response = _post(_client(), {"image_base64": _IMAGE})
    assert response.status_code == 200
    assert response.json()["reading"] == ""
    spend.assert_awaited_once()


def test_scan_read_past_the_deadline_degrades_to_an_empty_reading() -> None:
    async def slow_read(*_args: Any, **_kwargs: Any) -> MathOcrResult:
        await asyncio.sleep(5)
        raise AssertionError("the deadline should have cut this read off")

    patches = _redis()
    with (
        patches[0],
        patches[1],
        patches[2] as spend,
        patches[3],
        patch("app.modules.math.api.extract_math_from_image", AsyncMock(side_effect=slow_read)),
    ):
        response = _post(
            _client(Settings(scan_read_deadline_seconds=0.05)), {"image_base64": _IMAGE}
        )
    assert response.status_code == 200
    assert response.json() == {"reading": "", "uncertain": True, "source": "none"}
    spend.assert_awaited_once()


def test_scan_read_gives_the_reader_what_is_left_of_one_deadline() -> None:
    empty = MathOcrResult(
        extract=None, display_text="", source="none", confidence=None, uncertain=True
    )
    patches = _redis()
    with patches[0], patches[1], patches[2], patches[3], _ocr(empty) as ocr:
        _post(_client(Settings(scan_read_deadline_seconds=12.0)), {"image_base64": _IMAGE})
    assert 0 < ocr.await_args.kwargs["timeout_seconds"] <= 12.0


@pytest.mark.parametrize(
    "subject, reader",
    [
        ("math", "app.modules.math.api.extract_math_from_image"),
        ("physics", "app.modules.physics.api.read_physics_problem"),
        ("chemistry", "app.modules.chemistry.api.read_chemistry_problem"),
    ],
)
def test_scan_rate_limit_is_one_per_user_budget_across_subjects(subject: str, reader: str) -> None:
    patches = _redis()
    client = _client(Settings(math_tools_enabled=True, chemistry_enabled=True))
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3] as rate,
        patch(reader, AsyncMock(side_effect=RuntimeError("down"))),
    ):
        client.post(
            f"/{subject}/scan/read",
            headers={"Authorization": "Bearer tok"},
            json={"image_base64": _IMAGE},
        )
    assert rate.await_args is not None
    key = rate.await_args.args[1]
    assert key.startswith("scan_read_rl:")
    assert subject not in key


@pytest.mark.parametrize(
    "body, status",
    [
        ({"image_base64": "not base64!!"}, 400),
        ({"image_base64": ""}, 400),
        ({"image_base64": _IMAGE, "content_type": "application/pdf"}, 400),
        ({}, 400),
    ],
)
def test_scan_read_rejects_bad_payloads(body: dict[str, Any], status: int) -> None:
    patches = _redis()
    with patches[0], patches[1], patches[2], patches[3], _ocr(RuntimeError("unreached")) as ocr:
        response = _post(_client(), body)
    assert response.status_code == status
    ocr.assert_not_awaited()


def test_scan_read_rejects_an_oversized_image() -> None:
    big = base64.b64encode(b"\x00" * (SCAN_MAX_IMAGE_BYTES + 1)).decode()
    patches = _redis()
    with patches[0], patches[1], patches[2], patches[3], _ocr(RuntimeError("unreached")) as ocr:
        response = _post(_client(), {"image_base64": big})
    assert response.status_code == 413
    ocr.assert_not_awaited()


def test_scan_read_is_rate_limited_per_user() -> None:
    patches = _redis(allowed=False)
    with patches[0], patches[1], patches[2], patches[3], _ocr(RuntimeError("unreached")) as ocr:
        response = _post(_client(), {"image_base64": _IMAGE})
    assert response.status_code == 429
    ocr.assert_not_awaited()


def test_scan_read_stops_at_the_global_spend_cap() -> None:
    patches = _redis(spend_exceeded=True)
    with patches[0], patches[1], patches[2], patches[3], _ocr(RuntimeError("unreached")) as ocr:
        response = _post(_client(), {"image_base64": _IMAGE})
    assert response.status_code == 429
    ocr.assert_not_awaited()


def test_scan_read_is_off_with_math_tools() -> None:
    response = _post(_client(Settings(math_tools_enabled=False)), {"image_base64": _IMAGE})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("2*x+3 = 7", "2x+3 = 7"),
        ("x**2 - 5*x + 6 = 0", "x^2 - 5x + 6 = 0"),
        ("3 * (x + 1) = 9", "3(x + 1) = 9"),
        ("x*y = 4", "x*y = 4"),
        ("  y = 2*sin(x)  ", "y = 2sin(x)"),
    ],
)
def test_readable_reading(raw: str, shown: str) -> None:
    assert readable_reading(raw) == shown
