"""_style_format_hints: which layout, length and safety hints a turn gets.

BUG FIX regression: the short path used to append only SHORT_RESPONSE_FORMAT_HINT,
skipping MATH_SOLVER_HINT and the math half of INTENT_FORMAT_HINT entirely, so a short
maths turn got no guardrail against raw ```latex/```tex/```copy fences. The compact path
(greetings, fragments) is that short path now; there is no account-wide length setting.
"""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants import MATH_FENCE_SAFETY_HINT, UNIVERSAL_FORMAT_BASELINE
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.math.reply_policy import MATH_TUTORING_HINT, SHORT_MATH_SAFETY_HINT


def _hints(*, compact: bool = False) -> list[str]:
    return _style_format_hints(
        query_text="Solve 2x + 3 = 7",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=compact,
    )


def _day_plan_hints() -> list[str]:
    return _style_format_hints(
        query_text="plan my day",
        is_day_plan=True,
        minimal_personal_context=False,
    )


def test_day_plan_keeps_math_safety_guardrails():
    """BUG FIX (MATH-BE-033): day-plan turns used to get only
    FORMAT_CONTRACT, so a math question that landed in day-plan mode
    lost every guardrail against raw ```latex/```copy fences. The compact
    math safety hint now ships on day-plan turns too."""
    parts = _day_plan_hints()
    assert MATH_FENCE_SAFETY_HINT in parts
    joined = "\n".join(parts)
    assert "Do NOT emit ```answer" in joined
    assert "```latex" in joined


def test_compact_math_turn_still_includes_math_safety_guardrails():
    parts = _hints(compact=True)
    assert SHORT_MATH_SAFETY_HINT in parts
    joined = "\n".join(parts)
    assert "Do NOT emit ```answer" in joined
    assert "```latex" in joined


def test_compact_math_query_gets_step_hints_not_just_safety():
    from app.modules.math.reply_policy import (
        MATH_INTENT_HINT,
        MATH_SHORT_RESPONSE_HINT,
        MATH_SOLVER_HINT,
        MATH_TUTORING_HINT,
    )

    parts = _hints(compact=True)
    assert MATH_INTENT_HINT not in parts
    assert MATH_SOLVER_HINT not in parts
    assert MATH_TUTORING_HINT not in parts
    assert SHORT_MATH_SAFETY_HINT in parts
    assert MATH_SHORT_RESPONSE_HINT in parts
    assert "honor the user's brevity preference" in MATH_SHORT_RESPONSE_HINT
    assert "for steps, explanation, or a proof" in MATH_SHORT_RESPONSE_HINT
    assert "give a focused hint" in MATH_SHORT_RESPONSE_HINT


def test_rich_turn_injects_universal_format_baseline():
    from app.modules.chat.prompt_constants import UNIVERSAL_FORMAT_BASELINE

    parts = _hints()
    assert UNIVERSAL_FORMAT_BASELINE in parts
    joined = "\n".join(parts)
    assert (
        "Lead with the answer (a calculation leads with its working); explanation after." in joined
    )
    assert "[OpenAI docs](url)" in joined
    assert "do not add sections just to look structured" in joined


def test_closed_form_math_prompt_is_instance_first_not_a_lecture():
    """4! used to get 'start with n! definition + numbered steps + You can check'
    plus a fun-fact callout. Prompt now matches a one-line identity."""
    from app.modules.math.reply_policy import MATH_INTENT_HINT, SHORT_MATH_SAFETY_HINT

    assert "Closed-form" in SHORT_MATH_SAFETY_HINT
    from app.modules.math.reply_policy import GRAPH_NO_SUBSTITUTE_CLAUSE

    assert GRAPH_NO_SUBSTITUTE_CLAUSE in SHORT_MATH_SAFETY_HINT
    assert "$3 + 0 = 3$" in MATH_INTENT_HINT
    assert "$4! = 4 \\times 3 \\times 2 \\times 1 = 24$" in MATH_INTENT_HINT
    assert "no general" in MATH_INTENT_HINT
    assert "Never mention SymPy" in MATH_INTENT_HINT
    assert "You can check" not in MATH_INTENT_HINT
    assert "markdown checkbox" in MATH_INTENT_HINT
    # Old tutor shape must not return.
    assert "3! begins with" not in MATH_INTENT_HINT
    assert "Do not jump straight to the instance" not in MATH_INTENT_HINT


def test_funny_tone_does_not_pad_one_line_arithmetic() -> None:
    from app.modules.chat.response_tone import TONE_HINTS

    funny = TONE_HINTS["funny"]
    assert "3+0" in funny
    assert "one line" in funny
    assert "```tip" not in funny
    assert "occasional emoji" not in funny


# The emoji setting alone decides emoji; a tone that named them contradicted it.
def test_no_tone_speaks_about_emoji() -> None:
    from app.modules.chat.response_tone import TONE_HINTS

    for tone, hint in TONE_HINTS.items():
        assert "emoji" not in hint.lower(), tone


@pytest.mark.parametrize(
    ("level", "says"),
    [
        ("off", "Emoji: none."),
        ("some", "Emoji: a few"),
        ("more", "Emoji: plenty"),
        (None, "Emoji: a few"),
        ("unknown", "Emoji: a few"),
    ],
)
def test_the_emoji_setting_picks_one_line(level: str | None, says: str) -> None:
    from app.modules.chat.response_tone import emoji_hint

    assert emoji_hint(level).startswith(says)


# "A few" put 🌊 in the opening line too, and looked like "Lots".
def test_a_few_emoji_mark_only_headings_and_labels() -> None:
    from app.modules.chat.response_tone import emoji_hint

    some, more = emoji_hint("some"), emoji_hint("more")
    assert "none in a sentence, an opening line or a closing question" in some  # safety phrase
    assert "a short friendly line may carry one" in more  # safety phrase


@pytest.mark.parametrize("level", ["some", "more"])
def test_emoji_stay_out_of_what_is_read_exactly(level: str) -> None:
    from app.modules.chat.response_tone import emoji_hint

    hint = emoji_hint(level)
    for place in ("maths", "code", "fenced card", "worked maths", "draft", "painful"):
        assert place in hint, (level, place)


@pytest.mark.parametrize("level", ["off", "some", "more"])
def test_every_turn_carries_the_users_emoji_setting(level: str) -> None:
    from types import SimpleNamespace
    from typing import cast

    from app.modules.chat.prompt_sections import STABLE_SECTIONS, PromptTurn
    from app.modules.chat.response_tone import emoji_hint

    user = SimpleNamespace(
        response_tone="casual", emoji_use=level, custom_instructions=None, locale="en"
    )
    turn = cast("PromptTurn", SimpleNamespace(user=user))
    texts = [text for section in STABLE_SECTIONS[:2] for text in section.render(turn)]
    assert emoji_hint(level) in texts


# "Lead with the answer" and the tips list must not turn "I just got laid off" into a listicle.
@pytest.mark.parametrize(
    "query", ["I just got laid off and I'm freaking out", "my dog died this morning"]
)
def test_a_painful_message_is_acknowledged_before_the_help(query: str) -> None:
    hints = _style_format_hints(query_text=query, is_day_plan=False, minimal_personal_context=False)
    assert UNIVERSAL_FORMAT_BASELINE in hints
    assert "acknowledges" in UNIVERSAL_FORMAT_BASELINE


def test_rich_math_turn_keeps_full_math_solver_hint():
    parts = _hints()
    joined = "\n".join(parts)
    # Solve 2x+3=7 is math intent — full solver pack, not the compact safety blob.
    assert "Math diagrams and plots" in joined
    assert SHORT_MATH_SAFETY_HINT not in parts


def test_rich_math_turn_includes_math_tutoring_hint():
    """BUG FIX (MATH-E2E-004): the model used to just re-ask or hand over the
    answer when a user gave a wrong math answer. The tutoring hint now tells
    it to point to the wrong step and give a small hint first."""
    parts = _hints()
    joined = "\n".join(parts)
    assert MATH_TUTORING_HINT in joined
    assert "wrong" in joined.lower()


def test_slim_casual_turn_uses_compact_math_safety_not_viz_pack():
    """Help-me-think / slim chat must not dump the format+viz+solver bible."""
    from app.modules.chat.prompt_constants import FORMAT_CONTRACT, VISUALIZATION_HINTS
    from app.modules.math.reply_policy import MATH_SOLVER_HINT

    parts = _style_format_hints(
        query_text="I want to talk something through — ask me a good opening question.",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert MATH_FENCE_SAFETY_HINT in parts
    assert FORMAT_CONTRACT not in parts
    assert MATH_SOLVER_HINT not in parts
    assert VISUALIZATION_HINTS not in parts
    joined = "\n".join(parts)
    assert "Do NOT emit ```answer" in joined
    assert "Math diagrams and plots" not in joined


def test_compact_image_turn_gets_honesty_hint_not_viz_pack():
    from app.modules.chat.prompt_constants import (
        FORMAT_CONTRACT,
        IMAGE_GEN_HONESTY_HINT,
        VISUALIZATION_HINTS,
    )

    parts = _style_format_hints(
        query_text="Image",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert IMAGE_GEN_HONESTY_HINT in parts
    assert VISUALIZATION_HINTS not in parts
    assert FORMAT_CONTRACT not in parts
    joined = "\n".join(parts)
    assert "Never send the user to DALL-E" in joined  # safety phrase
    assert "Never say Recall cannot create or generate images" in joined  # safety phrase
    assert "do not tell them to send the same image request again" in joined


def test_compact_image_turn_when_generation_disabled_does_not_ask_to_retry():
    from app.modules.chat.prompt_constants import (
        IMAGE_GEN_HONESTY_HINT,
        IMAGE_GEN_UNAVAILABLE_HINT,
    )

    parts = _style_format_hints(
        query_text="generate an image of a dog",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
        image_generation_enabled=False,
    )
    assert IMAGE_GEN_UNAVAILABLE_HINT in parts
    assert IMAGE_GEN_HONESTY_HINT not in parts
    joined = "\n".join(parts)
    assert IMAGE_GEN_UNAVAILABLE_HINT in joined
    assert IMAGE_GEN_UNAVAILABLE_HINT in joined


def test_rich_turn_injects_format_contract_once_and_keeps_math():
    from app.modules.chat.prompt_constants import COMPARISON_FORMAT_HINT, FORMAT_CONTRACT
    from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_SOLVER_HINT

    parts = _hints()
    assert parts.count(FORMAT_CONTRACT) == 1
    assert MATH_INTENT_HINT in parts
    assert MATH_SOLVER_HINT in parts
    assert COMPARISON_FORMAT_HINT not in parts


def test_chart_query_gets_vega_fence_layout():
    from app.modules.chat.prompt_constants import (
        CHART_FORMAT_HINT,
        COMPACT_RESPONSE_FORMAT_HINT,
    )

    slim = _style_format_hints(
        query_text="Make a bar chart of average monthly rainfall in Seattle",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CHART_FORMAT_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT not in slim

    rich = _style_format_hints(
        query_text="Make a bar chart of average monthly rainfall in Seattle",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert CHART_FORMAT_HINT in rich


def test_mermaid_query_gets_flowchart_fence_layout():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        MERMAID_FORMAT_HINT,
    )

    slim = _style_format_hints(
        query_text="Draw a mermaid flowchart of making a cup of coffee",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert MERMAID_FORMAT_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT not in slim

    rich = _style_format_hints(
        query_text="Draw a mermaid flowchart of making a cup of coffee",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert MERMAID_FORMAT_HINT in rich


def test_one_sentence_skips_chart_and_compare_layout():
    from app.modules.chat.prompt_constants import (
        BREVITY_REQUEST_HINT,
        CHART_FORMAT_HINT,
        COMPACT_RESPONSE_FORMAT_HINT,
        COMPARISON_FORMAT_HINT,
    )
    from app.modules.turn_reading.length import is_brevity_request

    query = "In one sentence, make a bar chart of monthly rainfall"
    assert is_brevity_request(query)
    slim = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CHART_FORMAT_HINT not in slim
    assert COMPARISON_FORMAT_HINT not in slim
    assert BREVITY_REQUEST_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT in slim

    compare = _style_format_hints(
        query_text="tea versus coffee in one sentence",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert COMPARISON_FORMAT_HINT not in compare
    assert BREVITY_REQUEST_HINT in compare


def test_shorter_preserves_fact_guardrail():
    from app.modules.chat.prompt_constants import BREVITY_REQUEST_HINT
    from app.modules.turn_reading.length import is_brevity_request

    assert is_brevity_request("Shorter.")
    assert "never drop or blur factual details" in BREVITY_REQUEST_HINT
    assert "units" in BREVITY_REQUEST_HINT


def test_sequence_diagram_uses_sequence_hint_not_flowchart():
    from app.modules.chat.prompt_constants import MERMAID_FORMAT_HINT, SEQUENCE_FORMAT_HINT
    from app.modules.turn_reading.diagrams import is_sequence_diagram_question

    query = "sequence diagram of HTTP request"
    assert is_sequence_diagram_question(query)
    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert SEQUENCE_FORMAT_HINT in parts
    assert MERMAID_FORMAT_HINT not in parts
    assert "sequenceDiagram" in SEQUENCE_FORMAT_HINT
    joined = "\n".join(parts)
    assert MERMAID_FORMAT_HINT not in joined


def test_casual_tea_vs_coffee_skips_code_card_compare():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        COMPARISON_FORMAT_HINT,
    )
    from app.modules.turn_reading.format import is_structured_comparison_question

    query = "tea versus coffee"
    assert is_structured_comparison_question(query) is False
    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert COMPARISON_FORMAT_HINT not in parts
    assert COMPACT_RESPONSE_FORMAT_HINT in parts


def test_bare_rainfall_chart_still_gets_chart_hint():
    from app.modules.chat.prompt_constants import CHART_FORMAT_HINT

    parts = _style_format_hints(
        query_text="make a bar chart of monthly rainfall",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CHART_FORMAT_HINT in parts
    assert "sample data" in CHART_FORMAT_HINT
    assert "ask ONE question for the values" in CHART_FORMAT_HINT


def test_bare_email_asks_purpose_instead_of_inventing_a_draft():
    from app.modules.chat.prompt_constants.writing import EMAIL_ASK_PURPOSE_HINT, EMAIL_DRAFT_HINT

    parts = _style_format_hints(
        query_text="escribeme un correo",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert EMAIL_ASK_PURPOSE_HINT in parts
    assert EMAIL_DRAFT_HINT not in parts
    assert "escribeme un correo" in EMAIL_ASK_PURPOSE_HINT


def test_specified_email_still_drafts_now():
    from app.modules.chat.prompt_constants.writing import EMAIL_ASK_PURPOSE_HINT, EMAIL_DRAFT_HINT

    parts = _style_format_hints(
        query_text="email my boss about PTO",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert EMAIL_DRAFT_HINT in parts
    assert EMAIL_ASK_PURPOSE_HINT not in parts


def test_flowchart_of_making_coffee_gets_mermaid_hint():
    from app.modules.chat.prompt_constants import MERMAID_FORMAT_HINT

    parts = _style_format_hints(
        query_text="flowchart of making coffee",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert MERMAID_FORMAT_HINT in parts
    assert 'E["Grind beans"]' in MERMAID_FORMAT_HINT


def test_callout_query_gets_blockquote_layout():
    from app.modules.chat.prompt_constants import (
        CALLOUT_FORMAT_HINT,
        COMPACT_RESPONSE_FORMAT_HINT,
    )

    query = (
        "Give me 3 tips for staying focused while studying. Include a warning about all-nighters."
    )
    slim = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CALLOUT_FORMAT_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT not in slim

    rich = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert CALLOUT_FORMAT_HINT in rich


def test_learning_plan_query_gets_complete_actionable_roadmap_policy():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        LEARNING_PLAN_HINT,
    )

    query = "Give me a 4-week plan to learn Spanish for travel."
    slim = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert LEARNING_PLAN_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT not in slim

    rich = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert LEARNING_PLAN_HINT in rich
    joined = "\n".join(rich)
    assert LEARNING_PLAN_HINT in joined
    assert "concrete example" in joined
    assert LEARNING_PLAN_HINT in joined


def test_vs_query_gets_table_with_conditional_code_examples():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        COMPARISON_FORMAT_HINT,
    )

    rich = _style_format_hints(
        query_text="Python vs Java",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert COMPARISON_FORMAT_HINT in rich
    assert "tagged code fences" in COMPARISON_FORMAT_HINT
    assert "materially help" in COMPARISON_FORMAT_HINT

    slim = _style_format_hints(
        query_text="Compare Python vs Java for a beginner. Side by side on typing, syntax, and use cases.",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert COMPARISON_FORMAT_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT not in slim
    joined = "\n".join(slim)
    assert "No ## headings" not in joined


def test_quote_query_gets_blockquote_layout():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        QUOTE_FORMAT_HINT,
    )

    query = "Give me a famous quote by Maya Angelou about courage, with attribution."
    slim = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert QUOTE_FORMAT_HINT in slim
    assert COMPACT_RESPONSE_FORMAT_HINT not in slim

    rich = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert QUOTE_FORMAT_HINT in rich


def test_integration_hints_wraps_todos_section():
    from app.core.config import Settings
    from app.modules.chat.prompt_context_hints import integration_hints

    parts = integration_hints(
        settings=Settings(
            web_search_enabled=False,
        ),
        query_text=None,
        local_tz="UTC",
        user_locale="en",
        location_for_context=None,
        prompt_location=None,
        memory_block="",
        attachment_rag_block="",
        todos_section="User Schedule\n### Today\n- ○ Milk at 09:00 (open, topic: Reminders)",
    )
    joined = "\n".join(parts)
    assert "[BEGIN UNTRUSTED CONTENT — schedule]" in joined
    assert "○ Milk" in joined


def test_explain_transformers_gets_format_contract_not_compact():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        FORMAT_CONTRACT,
        VISUALIZATION_HINTS,
    )
    from app.modules.math.reply_policy import MATH_SOLVER_HINT

    parts = _style_format_hints(
        query_text="explain how transformers work",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert FORMAT_CONTRACT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    assert MATH_SOLVER_HINT not in parts
    assert VISUALIZATION_HINTS not in parts
    joined = "\n".join(parts)
    assert "No ## headings" not in joined


def test_top_10_tips_gets_format_contract_not_compact():
    from app.modules.chat.prompt_constants import COMPACT_RESPONSE_FORMAT_HINT, FORMAT_CONTRACT
    from app.modules.math.reply_policy import MATH_SOLVER_HINT

    parts = _style_format_hints(
        query_text="give me the top 10 productivity tips",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert FORMAT_CONTRACT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    assert MATH_SOLVER_HINT not in parts
    joined = "\n".join(parts)
    assert "No ## headings" not in joined


def test_pasted_fragment_still_uses_compact():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        FORMAT_CONTRACT,
    )

    parts = _style_format_hints(
        query_text="Whoever made the best decision for me",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert COMPACT_RESPONSE_FORMAT_HINT in parts
    assert FORMAT_CONTRACT not in parts


def test_writing_caption_does_not_get_math_intent_pack():
    from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_SOLVER_HINT

    parts = _style_format_hints(
        query_text="write me a caption about a complex launch",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert MATH_INTENT_HINT not in parts
    assert MATH_SOLVER_HINT not in parts
    assert MATH_FENCE_SAFETY_HINT in parts
    joined = "\n".join(parts)
    assert "You can check" not in joined


# ── Per-turn length, openers and nearby contracts (PROMPT_SECTIONS) ─────────

_LESSON = (
    "### Lesson 1: The for loop\n\nA for loop repeats a block for each item.\n\n"
    "```quiz\nquestion: What does range(3) produce?\nanswer: 0, 1, 2\n```"
)


def _turn_prompt(
    query: str,
    *,
    exchange: tuple[tuple[str, str], ...] = (),
    lightweight: bool = False,
) -> tuple[str, str]:
    """(system prompt, nearby contracts) for one turn, from the real section tables."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.core.config import Settings
    from app.models.orm import User
    from app.modules.chat.prompt_format import render_rules
    from app.modules.chat.prompt_sections import (
        NEARBY_CONTRACTS,
        STABLE_SECTIONS,
        TURN_SECTIONS,
        PromptTurn,
    )

    user = User(
        id=uuid4(),
        name="Bini",
        email="bini@example.com",
        response_tone="casual",
        locale="en",
        timezone="UTC",
    )
    turn = PromptTurn(
        user=user,
        settings=Settings(_env_file=None, image_search_enabled=True),  # type: ignore[call-arg]
        query_text=query,
        local_tz="UTC",
        lightweight=lightweight,
        slim=True,
        recall_memory=False,
        advice_memory=False,
        minimal_personal_context=False,
        prompt_location=None,
        summary=None,
        memory_block="",
        attachment_rag_block="",
        todos_section=None,
        chat_history_rag_block="",
        exchange=[SimpleNamespace(role=role, content=text) for role, text in exchange],
        followup=None,
    )
    return (
        "\n\n".join(render_rules((*STABLE_SECTIONS, *TURN_SECTIONS), turn)),
        "\n\n".join(render_rules(NEARBY_CONTRACTS, turn)),
    )


def test_a_detail_request_gets_the_detailed_length_not_a_moderate_one():
    from app.modules.chat.prompt_constants import STYLE_HINTS

    system, _ = _turn_prompt("explain in detail how Raft handles split votes and partitions")
    assert "moderate in length" not in system
    assert STYLE_HINTS["detailed"] in system
    assert STYLE_HINTS["balanced"] not in system


def test_a_hard_question_without_a_length_word_may_still_go_deep():
    from app.modules.chat.prompt_constants import STYLE_HINTS

    system, _ = _turn_prompt("how does Raft handle split votes and network partitions?")
    assert STYLE_HINTS["balanced"] in system
    assert "hard, technical or multi-part one gets the depth it needs" in STYLE_HINTS["balanced"]
    assert "A simple question gets a short, direct answer" in STYLE_HINTS["balanced"]


def test_length_follows_the_message_not_an_account_setting():
    """The Short / Detailed account setting was retired (FEATURES.md, Personalization)."""
    from app.modules.chat.prompt_constants import STYLE_HINTS

    system, _ = _turn_prompt("how does Raft work?")
    assert STYLE_HINTS["balanced"] in system
    assert STYLE_HINTS["short"] not in system
    greeting, _ = _turn_prompt("hi", lightweight=True)
    assert STYLE_HINTS["short"] in greeting


def test_one_part_capped_and_one_part_detailed_gets_each_its_length():
    from app.modules.chat.prompt_constants import BREVITY_REQUEST_HINT, MIXED_LENGTH_HINT

    system, _ = _turn_prompt(
        "in one sentence what is DNS? Also explain in detail how TLS handshakes work"
    )
    assert MIXED_LENGTH_HINT in system
    assert BREVITY_REQUEST_HINT not in system
    capped, _ = _turn_prompt("summarize the french revolution in 3 sentences")
    assert BREVITY_REQUEST_HINT in capped and MIXED_LENGTH_HINT not in capped


def test_a_social_opener_gets_the_compact_prompt_and_no_photo():
    from app.modules.chat.prompt_constants import (
        ANSWER_PHOTO_HINT,
        COMPACT_RESPONSE_FORMAT_HINT,
        FORMAT_CONTRACT,
    )

    for opener in ("good morning!", "hello there", "how are you?"):
        system, _ = _turn_prompt(opener)
        assert COMPACT_RESPONSE_FORMAT_HINT in system, opener
        assert FORMAT_CONTRACT not in system, opener
        assert ANSWER_PHOTO_HINT not in system, opener
    question, _ = _turn_prompt("good morning, what's the capital of Peru?")
    assert FORMAT_CONTRACT in question
    assert COMPACT_RESPONSE_FORMAT_HINT not in question


def test_a_correction_contract_sits_beside_the_user_turn():
    from app.modules.chat.prompt_constants import CORRECTION_HINT

    asked = (("user", "what should I cook tonight?"), ("assistant", "Lemon chicken or beef?"))
    system, nearby = _turn_prompt("no, I said I'm vegetarian", exchange=asked)
    assert CORRECTION_HINT in nearby and CORRECTION_HINT not in system
    assert "do not repeat the mistaken assumption" in CORRECTION_HINT
    assert "without a long apology" in CORRECTION_HINT
    # Nothing was said yet to correct, and a thank-you closes the topic.
    assert CORRECTION_HINT not in _turn_prompt("no, I said I'm vegetarian")[1]
    assert CORRECTION_HINT not in _turn_prompt("no, I said it was fine — thanks", exchange=asked)[1]


def test_continue_resumes_the_last_reply_but_a_lesson_keeps_its_own_next_step():
    from app.modules.chat.prompt_constants import ANSWER_PHOTO_HINT, CONTINUE_HINT

    story = (("user", "tell me a story"), ("assistant", "Once upon a time, a dragon named"))
    system, nearby = _turn_prompt("continue", exchange=story)
    assert CONTINUE_HINT in nearby
    assert ANSWER_PHOTO_HINT not in system
    assert "Do not restart, recap, or repeat" in CONTINUE_HINT
    lesson = (("user", "teach me python loops"), ("assistant", _LESSON))
    assert CONTINUE_HINT not in _turn_prompt("continue", exchange=lesson)[1]
    assert CONTINUE_HINT not in _turn_prompt("continue")[1]
    assert CONTINUE_HINT not in _turn_prompt("another one", exchange=story)[1]
