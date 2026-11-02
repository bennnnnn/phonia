"""Tests for app.modules.billing.plan — plan gates and model pools."""

from typing import Any

import pytest

from app.core.config import Settings
from app.models import model_catalog
from app.models.routing_lanes import ROUTING
from app.modules.billing import plan as plan_service
from app.modules.chat.model_routing import choice as model_choice
from app.tests.fakes import make_user


class FakeUser:
    plan = "free"


class ProUser(FakeUser):
    plan = "pro"


def test_free_pool_uses_cheapest_models():
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    pool = plan_service.free_pool(settings)
    assert "free-chat" in pool
    assert "smart-chat" not in pool


def test_free_user_auto_routes_within_pool():
    user = FakeUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_user_model(user, "explain quantum physics", settings)
    assert resolved in plan_service.free_pool(settings)


def test_pro_user_auto_can_pick_smart():
    user = ProUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_user_model(user, "debug this crash", settings)
    assert resolved == "smart-chat"


def test_regenerate_auto_reuses_prior_assistant_model():
    """A prior smart-chat reply → regenerate reuses smart-chat, not re-route."""
    user = ProUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    # "debug this crash" auto-routes to smart-chat; regenerate should reuse it
    # instead of re-running routing.
    resolved = model_choice.resolve_regenerate_model(
        user, "debug this crash", "smart-chat", settings
    )
    assert resolved == "smart-chat"


def test_regenerate_auto_falls_back_when_prior_model_unavailable():
    """If the prior model is no longer in the pool (e.g. downgrade), re-route."""
    user = FakeUser()  # free plan — smart-chat not allowed
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_regenerate_model(user, "hi", "smart-chat", settings)
    assert resolved != "smart-chat"
    assert resolved in plan_service.free_pool(settings)


def test_regenerate_auto_none_prior_falls_back_to_routing():
    """No prior assistant model (e.g. first turn failed) → normal routing."""
    user = ProUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_regenerate_model(user, "debug this crash", None, settings)
    assert resolved == model_choice.resolve_user_model(user, "debug this crash", settings)


def test_regenerate_auto_prior_is_auto_falls_back_to_routing():
    """If the stored prior model is itself "auto" (shouldn't happen), re-route."""
    user = ProUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_regenerate_model(user, "debug this crash", "auto", settings)
    assert resolved == model_choice.resolve_user_model(user, "debug this crash", settings)


def test_regenerate_ignores_pro_prior_model_on_free_plan():
    """Free user can't reuse a pro-only prior model — falls back to free pool."""
    user = FakeUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_regenerate_model(user, "hi", "smart-chat", settings)
    assert resolved != "smart-chat"
    assert resolved in plan_service.free_pool(settings)


def test_chat_fallback_models_skips_primary_and_respects_pool():
    user = ProUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    fallbacks = plan_service.chat_fallback_models(user, settings, "smart-chat")
    assert "smart-chat" not in fallbacks
    assert fallbacks
    assert fallbacks[0] in plan_service.model_pool(user, settings)


def test_free_user_hard_question_uses_strongest_in_pool():
    """Auto on a hard ask used to keep free-chat because the free pool has
    no smart-tier model and the miss fell through to cheapest. Use the
    strongest remaining alias (glm-5.3-flash, standard) instead."""
    user = FakeUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_user_model(user, "prove p = np", settings)
    pool = plan_service.free_pool(settings)
    assert resolved in pool
    assert model_catalog.tier_rank(model_catalog.get(resolved)) == max(
        model_catalog.tier_rank(model_catalog.get(mid)) for mid in pool
    )


def test_chat_fallback_models_prefer_nearby_tier_not_cheapest():
    """A dead smart-chat used to fail over to the cheapest aliases
    (free-chat, then a standard model). Stay in the smart/max band first."""
    user = ProUser()
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    fallbacks = plan_service.chat_fallback_models(user, settings, "smart-chat")
    assert fallbacks
    assert "smart-chat" not in fallbacks
    # The other smart model first, then the nearest tier — never straight to the cheapest.
    assert model_catalog.get(fallbacks[0]).tier in {"smart", "max"}
    ranks = [model_catalog.tier_rank(model_catalog.get(mid)) for mid in fallbacks]
    assert ranks == sorted(ranks, reverse=True)


def _plan(plan: str) -> Any:
    return make_user(plan=plan)


_EVERYDAY = "hi, how is your day?"


@pytest.mark.parametrize(
    ("plan", "everyday"),
    [
        ("free", model_catalog.auto_fast_alias()),
        ("plus", model_catalog.auto_fast_alias()),
        # Pro's everyday turns get the stronger model (live 60-turn chat, 2026-10-25).
        ("pro", ROUTING.everyday_strong),
    ],
)
def test_auto_everyday_lane_follows_the_plan(plan: str, everyday: str) -> None:
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    assert model_choice.resolve_user_model(_plan(plan), _EVERYDAY, settings) == everyday


def test_pro_hard_and_maths_turns_keep_their_lanes() -> None:
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    user = _plan("pro")
    assert model_choice.resolve_user_model(user, "debug this crash", settings) == (
        model_catalog.auto_smart_alias()
    )
    assert model_choice.resolve_user_model(user, "solve x^2 - 5x + 6 = 0", settings) == (
        model_catalog.auto_math_alias()
    )


def test_pro_everyday_falls_back_when_the_strong_model_is_failing() -> None:
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    strong = ROUTING.everyday_strong
    failing = model_choice.resolve_user_model(
        _plan("pro"), _EVERYDAY, settings, unhealthy=frozenset({strong})
    )
    assert failing != strong


def test_pro_everyday_keeps_a_photo_turn() -> None:
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    strong = ROUTING.everyday_strong
    user = _plan("pro")
    assert plan_service.image_turn_model(user, settings, strong) == strong
    assert (
        plan_service.image_turn_model(user, settings, strong, unhealthy=frozenset({strong}))
        != strong
    )
    # Another plan routed to that model (a fallback, a regenerate) still gets the photo lane.
    lane = plan_service.image_turn_model(_plan("free"), settings, strong)
    assert lane == model_catalog.vision_alias()


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        ("pro", ROUTING.everyday_strong),
        ("free", model_catalog.auto_fast_alias()),
    ],
)
def test_regenerating_a_cheap_everyday_reply_follows_the_plan(plan: str, expected: str) -> None:
    """Review: "try again" on Pro reused the Qwen reply's model."""
    settings = Settings(mock_llm_enabled=True, openrouter_api_key="")
    resolved = model_choice.resolve_regenerate_model(
        _plan(plan), _EVERYDAY, model_catalog.auto_fast_alias(), settings
    )
    assert resolved == expected


def test_the_strong_everyday_switch_is_read_per_plan() -> None:
    off = Settings(mock_llm_enabled=True, openrouter_api_key="", strong_everyday_model_pro=False)
    assert model_choice.resolve_user_model(_plan("pro"), _EVERYDAY, off) == (
        model_catalog.auto_fast_alias()
    )
    plus_on = Settings(
        mock_llm_enabled=True, openrouter_api_key="", strong_everyday_model_plus=True
    )
    assert model_choice.resolve_user_model(_plan("plus"), _EVERYDAY, plus_on) == (
        ROUTING.everyday_strong
    )
