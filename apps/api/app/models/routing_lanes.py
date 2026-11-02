"""The aliases routing picks by job: data, changed here and not in routing code.

``app.models.model_catalog`` serves Auto's, the photo and the tool lanes
(``auto_fast_alias``, ``vision_alias``, ``tool_selector_aliases``, ...); a background
job reads its own lane (``ROUTING.background``). ``test_model_catalog`` checks each lane
against the capability its job needs, so a lane can't point at a model that can't do it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingLanes:
    """One product alias per job (Auto's three lanes, photos, tools, background calls)."""

    # Qwen3.7 Flash answers an everyday turn as fast as GPT-6 Luna (about 0.8s to
    # first text with thinking off) for about a third of the price. Auto's
    # everyday lane carries most turns; hard and maths turns route stronger.
    everyday: str
    # Auto's everyday lane on a plan that includes the stronger one (Pro:
    # ``entitlements.has_strong_everyday_model``). A 60-turn live chat on Qwen3.7 Flash
    # (2026-10-25) named the wrong author for a book, called a 2026 TV season
    # unaired, told the user they had a game result wrong against its own sources,
    # and wrote a web_search fence as text instead of searching. Claude Haiku 5.5
    # answers everyday turns carefully at a few times Qwen's price per token.
    everyday_strong: str
    hard: str
    # Live phone QA repeatedly saw DeepSeek R1 stream hidden reasoning and then
    # return no visible answer. GLM 5.2 produced the verified worked-math
    # contract in about two seconds, so Auto math uses this strong tier directly.
    math: str
    # A turn that shows the model a photo, when its own model cannot read one,
    # and the second photo reader (another company) when the first fails.
    vision: str
    vision_backup: str
    # The tool-selection round, in order: one fast tool-capable model, then one
    # from another company when the first fails.
    tool_selectors: tuple[str, ...]
    # A background structured call (memory, titles, word problems) asks this once when
    # its own model fails or answers out of shape. It must do JSON mode.
    structured_fallback: str
    # Background jobs: memory's facts and sections, a chat's summary, the follow-up
    # questions under a reply, and which earlier chat a message means. JSON mode.
    background: str
    # A new chat's title.
    titles: str
    # A word problem turned into equations, and the maths read when the rules find none.
    # Both run before the reply's first text, so a fast model; its output is only a
    # candidate (number grounding and SymPy check it). JSON mode.
    word_problems: str
    math_extract: str


ROUTING = RoutingLanes(
    everyday="qwen-3.7-flash",
    everyday_strong="free-chat",
    hard="smart-chat",
    math="glm-5.2",
    vision="vision-chat",
    vision_backup="fallback-vision-model",
    tool_selectors=("gpt-6-luna", "free-chat"),
    structured_fallback="fallback-memory-model",
    background="memory-model",
    titles="title-model",
    word_problems="gpt-6-luna",
    math_extract="gpt-6-luna",
)
