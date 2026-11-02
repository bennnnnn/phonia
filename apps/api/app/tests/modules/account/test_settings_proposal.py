"""A theme card: stored on the chat line, applied only when the user taps it."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.account.settings_intent import SettingsChange
from app.modules.account.settings_proposal import (
    SettingsProposalError,
    confirm_proposal,
    format_proposal_reply,
    materialize_settings_reply,
    validate_changes,
)
from app.tests.fakes import redis_mock


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


@pytest.mark.parametrize(("value", "applied"), [("dark", "dark"), ("default", "system")])
def test_validate_keeps_a_theme_and_reads_default_as_the_system_theme(
    value: str, applied: str
) -> None:
    assert validate_changes([SettingsChange("appearance", value)]) == [
        SettingsChange("appearance", applied)
    ]


def test_validate_never_applies_another_field() -> None:
    other = SettingsChange("response_tone", "funny")  # type: ignore[arg-type]
    assert validate_changes([other, SettingsChange("appearance", "neon")]) == []


def test_format_proposal_includes_fence() -> None:
    text = format_proposal_reply(proposal_id="abc", apply=[SettingsChange("appearance", "dark")])
    assert text.startswith("I can switch that for you: Appearance → Dark.")
    assert "```settings_proposal" in text
    assert '"proposal_id": "abc"' in text


@pytest.mark.asyncio
async def test_materialize_stores_redis() -> None:
    redis = redis_mock()
    reply = await materialize_settings_reply(
        redis,
        _user(),  # type: ignore[arg-type]
        [SettingsChange("appearance", "dark")],
    )
    assert reply is not None and "settings_proposal" in reply
    redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_applies_the_theme_and_nothing_else() -> None:
    redis = redis_mock()
    redis.set = AsyncMock(return_value=True)
    redis.getdel = AsyncMock(return_value=b"1")
    # A card stored before chat stopped changing other settings.
    redis.get = AsyncMock(
        return_value=b'[{"field":"response_tone","value":"casual"},{"field":"appearance","value":"dark"}]'
    )
    user = _user()
    result = await confirm_proposal(redis, user, "pid")  # type: ignore[arg-type]

    assert result["appearance"] == "dark"
    assert result["user"] is user
    assert [item["field"] for item in result["applied"]] == ["appearance"]


@pytest.mark.asyncio
async def test_an_old_card_for_another_setting_is_not_confirmed() -> None:
    redis = redis_mock()
    redis.get = AsyncMock(return_value=b'[{"field":"default_model","value":"smart-chat"}]')
    with pytest.raises(SettingsProposalError):
        await confirm_proposal(redis, _user(), "pid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_confirm_expired_raises() -> None:
    redis = redis_mock()
    redis.get = AsyncMock(return_value=None)
    with pytest.raises(SettingsProposalError):
        await confirm_proposal(redis, _user(), "gone")  # type: ignore[arg-type]
