"""Per-user model pools, and picks within one by tier and price.

Plan policy itself lives in ``entitlements``. Which model a message needs is chat's
(``modules/chat/model_routing``): billing reads no message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard

from app.core.config import Settings
from app.models import model_catalog
from app.models.routing_lanes import ROUTING
from app.modules.billing.entitlements import can_use, has_strong_everyday_model, is_paid
from app.services import model_health

if TYPE_CHECKING:
    from app.models.orm import User

__all__ = [
    "AUTO_ALIAS",
    "allowed_model_ids",
    "can_use",
    "chat_fallback_models",
    "default_pro_enabled",
    "free_pool",
    "image_turn_model",
    "is_auto_enabled",
    "is_explicit_pick",
    "is_paid",
    "model_pool",
    "override_pool",
    "pick_cheapest_from_pool",
    "pick_fast_from_pool",
    "pick_preferred_tier",
    "pick_smart_from_pool",
    "pick_strongest_from_pool",
    "validate_enabled_models_for_update",
]

AUTO_ALIAS = "auto"


def free_pool(settings: Settings) -> list[str]:
    """Cheapest models available on the free plan."""
    candidates = [
        m
        for m in model_catalog.selectable_models()
        if m.plan_access == "free" and model_health.is_available(m, settings)
    ]
    if not candidates:
        fallback = model_catalog.get(model_catalog.auto_fast_alias())
        if model_health.is_available(fallback, settings):
            return [fallback.id]
        return [model_catalog.auto_fast_alias()]
    candidates.sort(key=model_catalog.price_sort_key)
    return [m.id for m in candidates]


def default_pro_enabled(settings: Settings) -> list[str]:
    return [
        m.id for m in model_catalog.selectable_models() if model_health.is_available(m, settings)
    ]


def allowed_model_ids(user: User, settings: Settings) -> set[str]:
    if can_use(user, "all_models", settings):
        return {
            m.id
            for m in model_catalog.selectable_models()
            if model_health.is_available(m, settings)
        }
    return set(free_pool(settings))


def is_auto_enabled(user: User) -> bool:
    if user.enabled_models is None:
        return True
    return AUTO_ALIAS in user.enabled_models


def models_choosing(user: User, settings: Settings, model_id: str) -> list[str]:
    """``enabled_models`` after choosing ``model_id``, the one rule for every chooser.

    Auto keeps (or restores) the pool with Auto on. A model moves to the front with
    Auto off and the rest of the pool kept, so the user's other switches survive.
    """
    if model_id == AUTO_ALIAS:
        current = user.enabled_models
        if current and AUTO_ALIAS in current:
            return list(current)
        pool = model_pool(user, settings)
        return validate_enabled_models_for_update(user, [AUTO_ALIAS, *pool], settings) or [
            AUTO_ALIAS
        ]
    if model_id not in allowed_model_ids(user, settings):
        raise ValueError("That model isn't available on your plan.")
    rest = [item for item in model_pool(user, settings) if item != model_id]
    return validate_enabled_models_for_update(user, [model_id, *rest], settings) or [model_id]


def model_pool(user: User, settings: Settings) -> list[str]:
    """Concrete model aliases Recall may use (never includes ``auto``)."""
    allowed = allowed_model_ids(user, settings)
    stored = user.enabled_models
    if stored:
        pool = [model_id for model_id in stored if model_id != AUTO_ALIAS and model_id in allowed]
        if pool:
            return pool
    if can_use(user, "all_models", settings):
        enabled = [model_id for model_id in default_pro_enabled(settings) if model_id in allowed]
        return enabled or [model_catalog.auto_fast_alias()]
    return list(allowed) or [model_catalog.auto_fast_alias()]


def override_pool(user: User, settings: Settings) -> set[str]:
    """Models a per-message override may pick.

    This is ``model_pool`` (plan + the user's ``enabled_models`` preference),
    NOT ``allowed_model_ids`` (plan only): a model the user disabled in
    Settings must not be reachable via a WS/HTTP override even if their plan
    allows it. ``model_pool`` falls back to plan defaults when
    ``enabled_models`` is None, so default users keep the full plan pool.
    """
    return set(model_pool(user, settings))


def is_explicit_pick(model_alias: str | None) -> TypeGuard[str]:
    """The picker named one model for this message (not Auto, not unset)."""
    return bool(model_alias) and model_alias != AUTO_ALIAS


def image_turn_model(
    user: User,
    settings: Settings,
    routed: str,
    *,
    explicit: bool,
    unhealthy: frozenset[str] = frozenset(),
) -> str:
    """The model for a turn that shows the model an image: one that can read it.

    An explicit pick that reads images keeps the turn. Auto's hard lanes take the
    strongest healthy image reader above the everyday tier in the user's pool, so
    a hard question about a photo still gets a model that thinks. Everything else
    goes to the photo lane (``model_catalog.vision_alias``), or, while its breaker
    is open, straight to the backup it would fall back to.
    """
    vision = model_catalog.vision_alias()
    lane = vision
    if vision in unhealthy:
        backups = chat_fallback_models(
            user, settings, vision, max_fallbacks=1, unhealthy=unhealthy, needs_vision=True
        )
        lane = backups[0] if backups else vision
    if explicit:
        return routed if model_catalog.reads_images(routed) else lane
    if routed == vision or routed not in model_catalog.known_ids():
        return lane
    # Pro's everyday model reads photos itself: its turns keep it.
    if (
        routed == ROUTING.everyday_strong
        and has_strong_everyday_model(user, settings)
        and routed not in unhealthy
        and model_catalog.reads_images(routed)
    ):
        return routed
    everyday = model_catalog.tier_rank(model_catalog.get(model_catalog.auto_fast_alias()))
    if model_catalog.tier_rank(model_catalog.get(routed)) <= everyday:
        return lane
    readers = [
        model_id
        for model_id in model_pool(user, settings)
        if model_id not in unhealthy
        and model_catalog.reads_images(model_id)
        and model_catalog.tier_rank(model_catalog.get(model_id)) > everyday
    ]
    return pick_strongest_from_pool(readers) if readers else lane


def chat_fallback_models(
    user: User,
    settings: Settings,
    primary: str,
    *,
    max_fallbacks: int = 2,
    unhealthy: set[str] | frozenset[str] | None = None,
    needs_vision: bool = False,
) -> list[str]:
    """Other models in the user's pool to try when the primary provider is down.

    ``unhealthy`` is a set of model aliases with poor health (high error rate
    or latency). When provided, unhealthy models are skipped so the fallback
    doesn't repeatedly hit a degraded provider. A model running the primary's
    own provider model is no backup. A turn that shows the model an image
    (``needs_vision``, or the photo lane as primary) falls back only to image
    readers, then to the photo lane's own backup.
    """
    if max_fallbacks <= 0:
        return []

    skip = unhealthy or set()
    known = model_catalog.known_ids()
    primary_model = model_catalog.get(primary) if primary in known else None
    needs_vision = needs_vision or primary == model_catalog.vision_alias()
    allowed = allowed_model_ids(user, settings)
    candidates: list[str] = []

    # The chat fallback pool is the user's other healthy selectable models, ordered
    # by tier proximity to the primary (cheapest-first failed a dead R1 over to the
    # weakest fast model). Background jobs' fallback is a lane of its own
    # (``structured_fallback``), never selectable and never in ``allowed``.
    for model_id in model_pool(user, settings):
        if model_id == primary or model_id in candidates:
            continue
        if model_id not in allowed or model_id in skip:
            continue
        model = model_catalog.get(model_id)
        if primary_model is not None and model.model == primary_model.model:
            continue
        if needs_vision and not model.supports_vision:
            continue
        if model_health.is_available(model, settings):
            candidates.append(model_id)

    primary_rank = model_catalog.tier_rank(primary_model) if primary_model is not None else 0

    def _fallback_sort_key(model_id: str) -> tuple[int, tuple[float, float, str]]:
        model = model_catalog.get(model_id)
        return (
            abs(model_catalog.tier_rank(model) - primary_rank),
            model_catalog.price_sort_key(model),
        )

    candidates.sort(key=_fallback_sort_key)
    if needs_vision:
        backup = model_catalog.get(model_catalog.vision_backup_alias())
        used = {model_catalog.get(model_id).model for model_id in candidates}
        if primary_model is not None:
            used.add(primary_model.model)
        if (
            backup.id not in skip
            and backup.model not in used
            and model_health.is_available(backup, settings)
        ):
            candidates.append(backup.id)
    return candidates[:max_fallbacks]


def validate_enabled_models_for_update(
    user: User,
    enabled_models: list[str] | None,
    settings: Settings,
) -> list[str] | None:
    if enabled_models is None:
        return None
    allowed = allowed_model_ids(user, settings)
    cleaned: list[str] = []
    for item in enabled_models:
        if item == AUTO_ALIAS:
            if AUTO_ALIAS not in cleaned:
                cleaned.append(AUTO_ALIAS)
            continue
        if item in allowed and item not in cleaned:
            cleaned.append(item)
    has_auto = AUTO_ALIAS in cleaned
    model_ids = [item for item in cleaned if item != AUTO_ALIAS]
    if not has_auto and not model_ids:
        raise ValueError("Turn on Auto or at least one model.")
    return cleaned


def _models_in_pool(pool: list[str]) -> list[model_catalog.ChatModel]:
    known = model_catalog.known_ids()
    return [model_catalog.get(model_id) for model_id in pool if model_id in known]


def pick_cheapest_from_pool(pool: list[str], settings: Settings | None = None) -> str:
    del settings
    models = _models_in_pool(pool)
    if not models:
        return pool[0]
    models.sort(key=model_catalog.price_sort_key)
    return models[0].id


def pick_fast_from_pool(pool: list[str]) -> str:
    models = _models_in_pool(pool)
    fast = [m for m in models if m.tier in {"fast", "standard"}]
    if fast:
        fast.sort(key=model_catalog.price_sort_key)
        return fast[0].id
    return pick_cheapest_from_pool(pool)


def pick_strongest_from_pool(pool: list[str]) -> str:
    """Best remaining model when the preferred smart/max alias is not in pool."""
    models = _models_in_pool(pool)
    if not models:
        return pool[0]
    models.sort(
        key=lambda m: (
            -model_catalog.tier_rank(m),
            -m.quota_multiplier,
            -model_catalog.price_sort_key(m)[0],
            -model_catalog.price_sort_key(m)[1],
            m.id,
        )
    )
    return models[0].id


def pick_smart_from_pool(pool: list[str]) -> str:
    models = _models_in_pool(pool)
    smart = [m.id for m in models if m.tier in {"smart", "max"}]
    if smart:
        return pick_strongest_from_pool(smart)
    return pick_strongest_from_pool(pool)


def pick_preferred_tier(preferred: str, pool: list[str]) -> str:
    """``preferred`` when the pool has it, else the pool's best model of its tier."""
    if preferred in pool:
        return preferred
    preferred_model = model_catalog.get(preferred)
    if preferred_model.tier in {"smart", "max"}:
        return pick_smart_from_pool(pool)
    return pick_fast_from_pool(pool)
