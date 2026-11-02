"""Thinking effort: only levels a model supports, and only as much as the turn needs."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.gateways.reasoning import EFFORTS, reasoning_body
from app.models import model_catalog
from app.modules.billing import plan as plan_service
from app.modules.chat.model_routing.route import resolve_alias_in_pool, route_chat_model
from app.modules.chat.model_routing.thinking import is_answer_dispute, thinking_level

# OpenRouter GET /api/v1/models, `reasoning` per slug, 2026-10-18. A model with
# no efforts listed takes only a disable or a token budget; a mandatory one
# rejects "none" and a disable.
SUPPORTED: dict[str, frozenset[str]] = {
    "anthropic/claude-haiku-5.5": frozenset({"max", "xhigh", "high", "medium", "low", "none"}),
    "deepseek/deepseek-v4.1-flash": frozenset({"max", "high", "low", "none"}),
    "z-ai/glm-5.3-flash": frozenset({"max", "high", "low"}),
    "z-ai/glm-5.2": frozenset({"xhigh", "high", "none"}),
    "openai/gpt-6-luna": frozenset({"max", "xhigh", "high", "medium", "low", "none"}),
    "qwen/qwen3.7-flash": frozenset(),
}
MANDATORY = frozenset({"z-ai/glm-5.3-flash"})

_SETTINGS = Settings(mock_llm_enabled=True, openrouter_api_key="")
_TRAIN = (
    "A train leaves at 3pm going 80 km/h; another leaves the same station at 4pm going "
    "120 km/h on the same track. When and where does the second catch the first?"
)


def _levels(model: model_catalog.ChatModel) -> dict[str, str | None]:
    return {
        "off": model.thinking_off,
        "hard": model.thinking_on,
        "escalate": model.thinking_escalate,
    }


@pytest.mark.parametrize("model", model_catalog.CATALOG, ids=lambda m: m.id)
def test_every_thinking_level_is_one_the_model_lists(model: model_catalog.ChatModel) -> None:
    slug = model_catalog.openrouter_slug(model.id)
    if slug not in SUPPORTED:
        assert not any(_levels(model).values()), f"{model.id}: add {slug} to SUPPORTED"
        return
    for level, value in _levels(model).items():
        if value is None:
            continue
        if value == "off":
            assert slug not in MANDATORY, f"{model.id} {level}: {slug} cannot disable thinking"
            continue
        assert value in EFFORTS
        assert value in SUPPORTED[slug], f"{model.id} {level}: {value!r} is not listed for {slug}"
        # "max" spends the most for no gain on the hard battery; never sent.
        assert value != "max"


def test_qwen_never_thinks_on_any_level() -> None:
    # Its thinking took 500-1500 tokens and 11 s to first text in live calls.
    for alias in ("qwen-3.7-flash", "title-model", "memory-model", "vision-chat"):
        model = model_catalog.get(alias)
        for level in ("off", "hard", "escalate"):
            body = reasoning_body(model, level)
            assert body in (None, {"enabled": False}), (alias, level)


@pytest.mark.parametrize(
    ("text", "prior", "level"),
    [
        ("hi", None, "off"),
        ("why is the sky blue", None, "off"),
        (_TRAIN, None, "hard"),
        ("that's wrong", "what is 17 * 23", "escalate"),
        ("are you sure?", "what is 17 * 23", "escalate"),
        ("try again", "what is 17 * 23", "escalate"),
        ("you made a mistake", "what is 17 * 23", "escalate"),
        ("wrong", "what is 17 * 23", "escalate"),
        # No answer before it: nothing to dispute.
        ("that's wrong", None, "off"),
        # A bare "no" answers an offer; "what's wrong with" asks for help.
        ("no", "want me to add a menu section?", "off"),
        ("what's wrong with my code?", None, "off"),
    ],
)
def test_thinking_level_escalates_only_on_a_disputed_answer(
    text: str, prior: str | None, level: str
) -> None:
    assert thinking_level(text, prior_user=prior, settings=_SETTINGS) == level


def test_regenerating_escalates() -> None:
    assert thinking_level("hi", regenerate=True, settings=_SETTINGS) == "escalate"


def test_a_disputed_answer_moves_to_the_thinking_tier() -> None:
    assert route_chat_model("that's wrong", prior_user="what is 17*23") == (
        model_catalog.auto_smart_alias()
    )
    assert route_chat_model("no", prior_user="want a menu?") == model_catalog.auto_fast_alias()


@pytest.mark.parametrize(
    ("text", "prior", "level", "free_body", "paid_body"),
    [
        ("hi", None, "off", {"enabled": False}, {"enabled": False}),
        (_TRAIN, None, "hard", {"effort": "low"}, {"effort": "low"}),
        ("that's wrong", "what is 17*23", "escalate", {"effort": "high"}, {"effort": "high"}),
    ],
)
def test_each_plan_gets_the_effort_its_lane_supports(
    text: str, prior: str | None, level: str, free_body: dict, paid_body: dict
) -> None:
    free = plan_service.free_pool(_SETTINGS)
    paid = [m.id for m in model_catalog.selectable_models()]
    assert thinking_level(text, prior_user=prior, settings=_SETTINGS) == level
    for pool, body in ((free, free_body), (paid, paid_body)):
        alias = resolve_alias_in_pool("auto", text, pool, _SETTINGS, prior_user=prior)
        assert reasoning_body(model_catalog.get(alias), level) == body, (pool, alias)


@pytest.mark.parametrize(
    "text",
    [
        "no",
        "nope",
        "what's wrong with my code",
        "the wrong number was dialed",
        "Is it wrong to eat late?",
    ],
)
def test_is_answer_dispute_leaves_ordinary_lines(text: str) -> None:
    assert not is_answer_dispute(text)


@pytest.mark.parametrize(
    "text",
    [
        "that's not what I asked",
        "this is not what I meant, I wanted the async version",
        "you misunderstood the question",
        "you misread it, the train leaves at 4pm",
        "I already told you the list can be empty",
        "that's wrong, it's 2024 not 2023",
    ],
)
def test_a_misread_question_or_an_ignored_correction_thinks_again(text: str) -> None:
    assert is_answer_dispute(text)
    assert thinking_level(text, prior_user="earlier question", settings=_SETTINGS) == "escalate"


@pytest.mark.parametrize(
    "text",
    [
        # A fact the model now applies; no harder thinking needed.
        "no, I said I'm vegetarian",
        "actually I meant Python 2, not 3",
        "I told you about my trip, right?",
    ],
)
def test_a_plain_correction_does_not_escalate(text: str) -> None:
    assert not is_answer_dispute(text)
