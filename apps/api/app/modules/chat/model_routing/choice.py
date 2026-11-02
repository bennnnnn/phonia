"""The model a turn runs on: billing's pool for the user, chat's routing for the message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.models import model_catalog
from app.models.routing_lanes import ROUTING
from app.modules.billing.entitlements import has_strong_everyday_model
from app.modules.billing.plan import AUTO_ALIAS, model_pool
from app.modules.chat.model_routing.route import resolve_alias_in_pool
from app.modules.chat.turn_trace import note_route

if TYPE_CHECKING:
    from app.models.orm import User


def resolve_user_model(
    user: User,
    content: str,
    settings: Settings,
    *,
    prior_user: str | None = None,
    prior_model: str | None = None,
    lesson_active: bool = False,
    unhealthy: frozenset[str] = frozenset(),
) -> str:
    """Auto's pick for this message from the plan's pool; there is no model setting.

    Auto skips models whose provider is failing (``unhealthy``) while a healthy
    one is left in the pool.
    """
    pool = model_pool(user, settings)
    routed = resolve_alias_in_pool(
        AUTO_ALIAS,
        content,
        pool,
        settings,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=lesson_active,
        unhealthy=unhealthy,
    )
    return _everyday_for_plan(user, settings, routed, pool, unhealthy)


def _everyday_for_plan(
    user: User, settings: Settings, routed: str, pool: list[str], unhealthy: frozenset[str]
) -> str:
    """Auto's everyday pick on a plan with the stronger everyday model (Pro).

    Only the everyday lane changes: hard and maths turns keep their lanes. The
    stronger model must be in the user's pool (they can switch it off) and healthy;
    otherwise the everyday model answers.
    """
    if routed != model_catalog.auto_fast_alias() or not has_strong_everyday_model(user, settings):
        return routed
    strong = ROUTING.everyday_strong
    return strong if strong in pool and strong not in unhealthy else routed


def resolve_regenerate_model(
    user: User,
    content: str,
    prior_assistant_model: str | None,
    settings: Settings,
) -> str:
    """Pick a model for a regenerate turn.

    Reuse the model that produced the prior assistant reply so "try again"
    reproduces the same conditions instead of re-running the routing heuristic
    — a borderline query that auto-routed to a smart model the first time would
    otherwise re-route to a weaker model on regenerate. Falls back to routing
    if the prior model is unknown or no longer in the user's pool.
    """
    pool = model_pool(user, settings)
    if (
        prior_assistant_model
        and prior_assistant_model != AUTO_ALIAS
        and prior_assistant_model in pool
    ):
        note_route("regenerate_same")
        # "Try again" on Pro after a cheap everyday reply (an older chat, or a fallback)
        # gets Pro's everyday model.
        return _everyday_for_plan(user, settings, prior_assistant_model, pool, frozenset())
    return resolve_user_model(user, content, settings)
