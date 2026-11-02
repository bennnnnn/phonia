"""POST /chemistry/scan/read returns the written problem as plain text."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.main import create_app
from app.models.orm import User
from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.direct import maybe_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.read import CHEMISTRY_READ_PROMPT
from app.services.scan_text import reading_from_vision

_IMAGE = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()


def _client() -> TestClient:
    user = MagicMock(spec=User)
    user.id = uuid4()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    return TestClient(app)


def _redis() -> Any:
    return (
        patch("app.services.scan_read.get_redis_client", return_value=MagicMock()),
        patch(
            "app.services.scan_read.quota_service.global_spend_exceeded",
            AsyncMock(return_value=False),
        ),
        patch(
            "app.services.scan_read.quota_service.record_global_spend",
            AsyncMock(return_value=0),
        ),
        patch("app.services.scan_read.allow_request_unless_down", AsyncMock(return_value=True)),
    )


def test_the_vision_prompt_asks_for_plain_text() -> None:
    assert "plain text" in CHEMISTRY_READ_PROMPT
    assert "Do not solve" in CHEMISTRY_READ_PROMPT
    assert "apparatus" in CHEMISTRY_READ_PROMPT
    assert "mathpix" not in CHEMISTRY_READ_PROMPT.casefold()
    assert "equation" not in CHEMISTRY_READ_PROMPT.casefold()


def test_a_math_kind_payload_is_not_a_chemistry_reading() -> None:
    raw = '{"kind":"equation","lhs":"2x+3","rhs":"7","found":true}'
    assert reading_from_vision(raw) == ""
    assert reading_from_vision("Find the molar mass of H2O") == "Find the molar mass of H2O"


def test_scan_read_returns_the_written_problem() -> None:
    patches = _redis()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch(
            "app.modules.chemistry.api.read_chemistry_problem",
            AsyncMock(return_value="Find the molar mass of H2O"),
        ) as read,
    ):
        response = _client().post(
            "/chemistry/scan/read",
            headers={"Authorization": "Bearer tok"},
            json={"image_base64": _IMAGE, "content_type": "image/jpeg"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "reading": "Find the molar mass of H2O",
        "uncertain": False,
        "source": "vision",
    }
    assert read.await_args is not None
    assert read.await_args.kwargs["content_type"] == "image/jpeg"


def test_a_confirmed_reading_solves_with_the_photo() -> None:
    from app.modules.chemistry.reading import chemistry_text_for_solve, confirmed_chemistry_reading
    from app.services.subject_scan import CHEMISTRY_CAMERA_PROMPT, SCAN_CONFIRMED_PREFIX

    caption = CHEMISTRY_CAMERA_PROMPT
    confirmed = f"{caption}\n\n{SCAN_CONFIRMED_PREFIX} Find the molar mass of H2O"
    assert confirmed_chemistry_reading(caption) is None
    assert chemistry_text_for_solve(confirmed) == "Find the molar mass of H2O"
    intent = extract_chemistry_intent(chemistry_text_for_solve(confirmed))
    assert intent is not None
    verified = build_verified_chemistry(intent)
    reply = maybe_direct_chemistry_reply(verified, has_image_attachment=True, user_text=confirmed)
    assert reply is not None
    assert "18.02" in reply
    assert (
        maybe_direct_chemistry_reply(verified, has_image_attachment=True, user_text=caption) is None
    )


def test_a_confirmed_reading_solves_as_typed_text_without_the_photo() -> None:
    reading = "Find the molar mass of H2O"
    assert not reading.startswith("Show steps:")
    intent = extract_chemistry_intent(reading)
    assert intent is not None
    verified = build_verified_chemistry(intent)
    reply = maybe_direct_chemistry_reply(verified, has_image_attachment=False)
    assert reply is not None
    assert "18.02" in reply
    assert maybe_direct_chemistry_reply(verified, has_image_attachment=True) is None
