"""Model choice by capability and health: photos, backups, failing providers, JSON asks."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.models import model_catalog
from app.modules.billing import plan as plan_service
from app.modules.chat.model_routing import choice as model_choice
from app.modules.chat.model_routing import route as routing

_SETTINGS = Settings(mock_llm_enabled=True, openrouter_api_key="")
_HARD = "plan a zero-downtime migration of a monolith Postgres schema to sharded tables"


def _User(plan: str = "pro", enabled: list[str] | None = None) -> Any:
    """A stand-in for the ORM user: the plan and the enabled models are all routing reads."""
    return SimpleNamespace(plan=plan, enabled_models=enabled)


def test_unhealthy_first_choice_is_skipped_for_a_healthy_strong_model() -> None:
    """R4.10: smart-chat's provider is failing; Auto's hard lane takes GLM 5.2."""
    user = _User()
    assert model_choice.resolve_user_model(user, _HARD, _SETTINGS) == "smart-chat"
    resolved = model_choice.resolve_user_model(
        user, _HARD, _SETTINGS, unhealthy=frozenset({"smart-chat"})
    )
    assert resolved == "glm-5.2"
    everyday = model_choice.resolve_user_model(
        user, "hi there", _SETTINGS, unhealthy=frozenset({"qwen-3.7-flash"})
    )
    assert everyday != "qwen-3.7-flash"
    assert model_catalog.get(everyday).tier in {"fast", "standard"}


def test_a_degraded_model_beats_none() -> None:
    user = _User(enabled=["auto", "smart-chat"])
    assert (
        model_choice.resolve_user_model(user, _HARD, _SETTINGS, unhealthy=frozenset({"smart-chat"}))
        == "smart-chat"
    )


def test_an_explicit_pick_is_kept_even_when_unhealthy() -> None:
    user = _User()
    picked = model_choice.resolve_user_model_override(
        user, "smart-chat", "hi", _SETTINGS, unhealthy=frozenset({"smart-chat"})
    )
    assert picked == "smart-chat"


def test_photo_turn_backups_all_read_images() -> None:
    """R4.13: a photo turn's backups can read the photo; qwen is vision-chat's own model."""
    fallbacks = plan_service.chat_fallback_models(_User(), _SETTINGS, "vision-chat")
    assert fallbacks
    assert all(model_catalog.reads_images(alias) for alias in fallbacks)
    assert "qwen-3.7-flash" not in fallbacks


def test_photo_turn_with_no_image_reader_enabled_uses_the_photo_backup() -> None:
    """The audit's probe: a Pro user with only Auto, smart-chat and GLM 5.2 enabled."""
    user = _User(enabled=["auto", "smart-chat", "glm-5.2"])
    assert plan_service.chat_fallback_models(user, _SETTINGS, "vision-chat") == [
        "fallback-vision-model"
    ]
    # A text turn keeps its usual backups.
    assert plan_service.chat_fallback_models(user, _SETTINGS, "smart-chat") == ["glm-5.2"]


def test_an_image_turn_on_an_explicit_reader_backs_up_to_readers() -> None:
    fallbacks = plan_service.chat_fallback_models(
        _User(), _SETTINGS, "gpt-6-luna", needs_vision=True
    )
    assert fallbacks
    assert all(model_catalog.reads_images(alias) for alias in fallbacks)


def test_photo_backup_never_repeats_the_primary_model() -> None:
    fallbacks = plan_service.chat_fallback_models(
        _User(enabled=["auto", "smart-chat"]),
        _SETTINGS,
        "fallback-vision-model",
        needs_vision=True,
    )
    assert fallbacks == []


@pytest.mark.parametrize(
    "routed, explicit, expected",
    [
        # An explicit pick that reads images keeps the photo turn.
        ("gpt-6-luna", True, "gpt-6-luna"),
        ("free-chat", True, "free-chat"),
        # One that cannot goes to the photo lane.
        ("smart-chat", True, "vision-chat"),
        # Auto's everyday lane: the photo lane (the same model, thinking off).
        ("qwen-3.7-flash", False, "vision-chat"),
        # Auto's hard lanes: the strongest image reader above the everyday tier.
        ("smart-chat", False, "glm-5.3-flash"),
        ("glm-5.2", False, "glm-5.3-flash"),
        # Already on the photo lane: stays.
        ("vision-chat", False, "vision-chat"),
    ],
)
def test_image_turn_model(routed: str, explicit: bool, expected: str) -> None:
    assert plan_service.image_turn_model(_User(), _SETTINGS, routed, explicit=explicit) == expected


def test_image_turn_model_skips_an_unhealthy_reader() -> None:
    assert (
        plan_service.image_turn_model(
            _User(), _SETTINGS, "smart-chat", explicit=False, unhealthy=frozenset({"glm-5.3-flash"})
        )
        == "vision-chat"
    )


@pytest.mark.parametrize(
    "routed, explicit",
    [("qwen-3.7-flash", False), ("vision-chat", False), ("smart-chat", True)],
)
def test_a_photo_turn_skips_an_open_photo_lane(routed: str, explicit: bool) -> None:
    """The photo lane shares the everyday lane's model, and its breaker: while it is
    open, a photo goes straight to the backup it would have fallen back to."""
    open_lane = frozenset({"qwen-3.7-flash", "vision-chat"})
    backups = plan_service.chat_fallback_models(
        _User(), _SETTINGS, "vision-chat", unhealthy=open_lane, needs_vision=True
    )
    model = plan_service.image_turn_model(
        _User(), _SETTINGS, routed, explicit=explicit, unhealthy=open_lane
    )
    assert model == backups[0]
    assert model not in open_lane and model_catalog.reads_images(model)


def test_is_explicit_pick() -> None:
    assert plan_service.is_explicit_pick("smart-chat")
    assert not plan_service.is_explicit_pick("auto")
    assert not plan_service.is_explicit_pick(None)
    assert not plan_service.is_explicit_pick("")


def test_a_json_ask_avoids_a_model_without_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """R4.9: the output format is a routing input; GLM 5.2's JSON mode is unconfirmed."""
    ask = "solve x^2 - 4 = 0 and give me the roots as valid JSON"
    pool = [model.id for model in model_catalog.selectable_models()]
    assert routing.resolve_alias_in_pool("auto", "solve x^2 - 4 = 0", pool) == "glm-5.2"
    assert model_catalog.get("glm-5.2").json_mode is False
    resolved = routing.resolve_alias_in_pool("auto", ask, pool)
    assert model_catalog.get(resolved).json_mode is True
    assert model_catalog.get(resolved).tier == "smart"


def test_a_json_ask_keeps_the_pool_when_no_model_has_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_json = {m.id: replace(m, json_mode=False) for m in model_catalog.CATALOG}
    monkeypatch.setattr("app.models.model_catalog._BY_ID", no_json)
    pool = ["qwen-3.7-flash", "smart-chat"]
    assert routing.resolve_alias_in_pool("auto", "list the planets as JSON", pool) in pool
