"""One source for the model a message uses: ``enabled_models``, and one rule to choose."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.schemas.auth import UserOut, chosen_model_id
from app.modules.account import lifecycle
from app.modules.billing import plan
from app.repositories import users as users_repo


@pytest.mark.parametrize(
    ("enabled", "chosen"),
    [
        (None, "auto"),
        (["auto", "free-chat"], "auto"),
        (["smart-chat", "free-chat"], "smart-chat"),
        ([], "auto"),
    ],
)
def test_the_chosen_model_is_auto_or_the_first_model_on(
    enabled: list[str] | None, chosen: str
) -> None:
    assert chosen_model_id(enabled) == chosen


def test_user_out_derives_default_model_from_enabled_models() -> None:
    out = UserOut(
        id=uuid4(),
        email="a@b.c",
        name=None,
        avatar_url=None,
        enabled_models=["glm-5.2", "free-chat"],
        memory_enabled=True,
        created_at=datetime.now(UTC),
    )
    assert out.default_model == "glm-5.2"
    assert out.model_dump()["default_model"] == "glm-5.2"


def _pro(enabled: list[str] | None) -> Any:
    return SimpleNamespace(plan="pro", enabled_models=enabled)


def test_choosing_a_model_puts_it_first_and_keeps_the_rest_of_the_pool() -> None:
    user = _pro(["auto", "free-chat", "smart-chat", "glm-5.2"])
    assert plan.models_choosing(user, Settings(), "glm-5.2") == [
        "glm-5.2",
        "free-chat",
        "smart-chat",
    ]


def test_choosing_auto_turns_auto_back_on_over_the_same_pool() -> None:
    user = _pro(["glm-5.2", "free-chat"])
    assert plan.models_choosing(user, Settings(), "auto") == ["auto", "glm-5.2", "free-chat"]


def test_a_model_outside_the_plan_is_refused() -> None:
    free: Any = SimpleNamespace(plan="free", enabled_models=None)
    with pytest.raises(ValueError, match="isn't available"):
        plan.models_choosing(free, Settings(), "gpt-6-luna")


async def test_the_stored_copy_follows_every_write_of_enabled_models() -> None:
    user: Any = SimpleNamespace(id=uuid4(), default_model="auto", enabled_models=None)
    # No sync_session: the user is written as-is; flush is all an unsaved write does.
    session: Any = SimpleNamespace(flush=AsyncMock())
    await users_repo.update(session, user, commit=False, enabled_models=["smart-chat"])
    assert user.default_model == "smart-chat"


async def test_an_older_apps_default_model_patch_chooses_through_the_same_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: dict[str, Any] = {}

    async def update(_session: Any, user: Any, **fields: Any) -> Any:
        written.update(fields)
        return user

    monkeypatch.setattr(lifecycle.users_repo, "update", update)
    user = _pro(["auto", "free-chat", "glm-5.2"])
    user.memory_enabled = True
    await lifecycle.update_account(AsyncMock(), user, Settings(), {"default_model": "glm-5.2"})
    assert written["enabled_models"] == ["glm-5.2", "free-chat"]
    assert "default_model" not in written  # the repository writes the copy
