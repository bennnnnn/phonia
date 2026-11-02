"""Plans, features and per-plan allowances: the one place plan policy lives.

Three plans: ``free``, ``plus`` (the lower paid plan) and ``pro`` (the top
plan). Display names ("Plus", "Pro") live only in the app's i18n; the server
speaks in plan ids.

Every number is a ``core/config.py`` setting, named ``<base>`` for free,
``<base>_plus`` and ``<base>_pro``. A metered feature is part of a plan when
that plan's allowance is above zero, so moving a feature between plans is a
config change, not a code change. Callers ask ``can_use(user, feature)`` and
``allowance(user, name)``; nothing else reads ``user.plan``.

Kept free of heavy imports: schemas and quota code import it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, get_args

if TYPE_CHECKING:
    from app.core.config import Settings

PlanId = Literal["free", "plus", "pro"]
PLANS: tuple[PlanId, ...] = get_args(PlanId)
PAID_PLANS: frozenset[str] = frozenset({"plus", "pro"})

Feature = Literal[
    "all_models",
    "image_generation",
    "speech_transcription",
    "speech_tts",
    "live_talk",
]
FEATURES: tuple[Feature, ...] = get_args(Feature)

Allowance = Literal[
    "daily_tokens",
    "daily_image_uploads",
    "daily_document_uploads",
    "daily_web_searches",
    "daily_image_searches",
    "daily_image_generations",
    "daily_speech_transcriptions",
    "daily_speech_tts",
    "monthly_live_talk_minutes",
]
ALLOWANCES: tuple[Allowance, ...] = get_args(Allowance)

# Allowance → the free-plan Settings field; ``_plus`` / ``_pro`` follow it.
_ALLOWANCE_SETTING: dict[Allowance, str] = {
    "daily_tokens": "daily_token_limit",
    "daily_image_uploads": "daily_image_limit",
    "daily_document_uploads": "daily_document_limit",
    "daily_web_searches": "daily_tavily_searches",
    "daily_image_searches": "daily_image_searches",
    "daily_image_generations": "daily_image_generations",
    "daily_speech_transcriptions": "daily_speech_transcriptions",
    "daily_speech_tts": "daily_speech_tts",
    "monthly_live_talk_minutes": "monthly_live_talk_minutes",
}

# Metered features: included when the plan's allowance is above zero.
_FEATURE_ALLOWANCE: dict[Feature, Allowance] = {
    "image_generation": "daily_image_generations",
    "speech_transcription": "daily_speech_transcriptions",
    "speech_tts": "daily_speech_tts",
    "live_talk": "monthly_live_talk_minutes",
}


class _HasPlan(Protocol):
    plan: str


def plan_of(subject: _HasPlan | str | None) -> PlanId:
    """The user's plan id. Anything unknown is ``free`` (never a paid plan)."""
    raw = subject if isinstance(subject, str) or subject is None else subject.plan
    value = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if value == "plus":
        return "plus"
    if value == "pro":
        return "pro"
    return "free"


def is_paid(subject: _HasPlan | str | None) -> bool:
    return plan_of(subject) in PAID_PLANS


def setting_name(name: Allowance, plan: PlanId) -> str:
    base = _ALLOWANCE_SETTING[name]
    return base if plan == "free" else f"{base}_{plan}"


def has_strong_everyday_model(subject: _HasPlan | str | None, settings: Settings) -> bool:
    """Auto answers this plan's everyday turns with the stronger model.

    A switch per plan (``strong_everyday_model``, ``_plus``, ``_pro``), read like an
    allowance's numbers. Not a ``Feature``: the app shows nothing for it.
    """
    plan = plan_of(subject)
    name = "strong_everyday_model" if plan == "free" else f"strong_everyday_model_{plan}"
    return bool(getattr(settings, name))


def allowance(subject: _HasPlan | str | None, name: Allowance, settings: Settings) -> int:
    """This plan's number for *name* (a daily cap, or monthly minutes). Never negative."""
    value = getattr(settings, setting_name(name, plan_of(subject)))
    return max(0, int(value))


def can_use(subject: _HasPlan | str | None, feature: Feature, settings: Settings) -> bool:
    """True when the plan includes *feature*. Global ``*_enabled`` flags are separate."""
    if feature == "all_models":
        return is_paid(subject)
    return allowance(subject, _FEATURE_ALLOWANCE[feature], settings) > 0


def features_for(subject: _HasPlan | str | None, settings: Settings) -> list[Feature]:
    return [feature for feature in FEATURES if can_use(subject, feature, settings)]


def plan_catalog(settings: Settings) -> list[dict[str, object]]:
    """Every plan with its features and numbers, for the paywall."""
    return [
        {
            "id": plan,
            "features": features_for(plan, settings),
            "allowances": {name: allowance(plan, name, settings) for name in ALLOWANCES},
        }
        for plan in PLANS
    ]


def plan_from_entitlements(active: set[str], settings: Settings) -> PlanId:
    """Highest plan whose RevenueCat entitlement is active.

    The Pro entitlement keeps its original id (``revenuecat_entitlement_id``),
    so every subscriber from the single-plan era stays on the top plan.
    """
    if settings.revenuecat_entitlement_id in active:
        return "pro"
    if settings.revenuecat_plus_entitlement_id in active:
        return "plus"
    return "free"
