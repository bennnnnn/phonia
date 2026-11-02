"""The model a turn runs on: billing's pool for the user, chat's routing for the message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.exceptions import UnknownModelOverrideError
from app.models import model_catalog
from app.models.routing_lanes import ROUTING
from app.modules.billing.entitlements import has_strong_everyday_model
from app.modules.billing.plan import (
    AUTO_ALIAS,
    is_auto_enabled,
    is_explicit_pick,
    model_pool,
    override_pool,
    pick_cheapest_from_pool,
)
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
    """Pick a concrete model from the user's Settings preferences.

    Auto skips models whose provider is failing (``unhealthy``) while a healthy
    one is left in the pool.
    """
    pool = model_pool(user, settings)
    if is_auto_enabled(user):
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
    note_route("single_model" if len(pool) == 1 else "cheapest")
    if len(pool) == 1:
        return pool[0]
    return pick_cheapest_from_pool(pool, settings)


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


def resolve_user_model_override(
    user: User,
    model_alias: str | None,
    content: str,
    settings: Settings,
    *,
    prior_user: str | None = None,
    prior_model: str | None = None,
    lesson_active: bool = False,
    unhealthy: frozenset[str] = frozenset(),
) -> str:
    """Pick a concrete model, honoring a per-message override when allowed.

    A per-chat/per-message picker passes ``model_alias`` over the WS. Use it
    only if it's a concrete alias the user has enabled (and their plan allows).
    ``auto`` and ``None`` route within the Settings pool. A concrete alias
    that is not in that pool raises rather than silently switching models.
    """
    if is_explicit_pick(model_alias):
        if model_alias not in override_pool(user, settings):
            raise UnknownModelOverrideError(model_alias)
        note_route("explicit_pick")
        return model_alias
    return resolve_user_model(
        user,
        content,
        settings,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=lesson_active,
        unhealthy=unhealthy,
    )


def resolve_regenerate_model(
    user: User,
    model_alias: str | None,
    content: str,
    prior_assistant_model: str | None,
    settings: Settings,
) -> str:
    """Pick a model for a regenerate turn.

    Honors an explicit concrete override (a per-message picker pick) just like
    ``resolve_user_model_override``. When the picker is ``auto`` (or absent),
    reuse the model that produced the prior assistant reply so "try again"
    reproduces the same conditions instead of re-running the routing heuristic
    — a borderline query that auto-routed to a smart model the first time would
    otherwise re-route to a weaker model on regenerate. Falls back to routing
    if the prior model is unknown or no longer in the user's enabled pool.
    """
    pool = override_pool(user, settings)
    if is_explicit_pick(model_alias):
        if model_alias not in pool:
            raise UnknownModelOverrideError(model_alias)
        note_route("explicit_pick")
        return model_alias
    if (
        prior_assistant_model
        and prior_assistant_model != AUTO_ALIAS
        and prior_assistant_model in pool
    ):
        note_route("regenerate_same")
        # "Try again" on Pro after a cheap everyday reply (an older chat, or a fallback)
        # gets Pro's everyday model.
        if not is_auto_enabled(user):
            return prior_assistant_model
        return _everyday_for_plan(user, settings, prior_assistant_model, list(pool), frozenset())
    return resolve_user_model(user, content, settings)
