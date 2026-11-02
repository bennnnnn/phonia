"""Casual/slim turns must stay ChatGPT-shaped — not a funny table essay."""

import pytest

from app.modules.chat.prompt_constants import (
    COMPACT_RESPONSE_FORMAT_HINT,
    FORMAT_CONTRACT,
    MATH_FENCE_SAFETY_HINT,
    TONE_FORMAT_GUARD,
    UNIVERSAL_FORMAT_BASELINE,
    WRITING_LINE_HINT,
    is_bare_writing_line,
)
from app.modules.chat.prompt_format import _style_format_hints


def test_compact_turn_skips_rich_format_pack():
    parts = _style_format_hints(
        query_text="Whoever made the best decision for me",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert COMPACT_RESPONSE_FORMAT_HINT in parts
    assert FORMAT_CONTRACT not in parts
    assert MATH_FENCE_SAFETY_HINT in parts
    joined = "\n".join(parts)
    assert "Make answers visually clear" not in joined
    assert "do not invent a topic essay" in joined.lower()


def test_compact_technical_compare_uses_table_and_conditional_code_examples():
    from app.modules.chat.prompt_constants import COMPARISON_FORMAT_HINT

    parts = _style_format_hints(
        query_text="Compare Python vs Java for a beginner. Side by side on typing, syntax, and use cases.",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert COMPARISON_FORMAT_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    joined = "\n".join(parts)
    assert COMPARISON_FORMAT_HINT in joined
    assert "only when" in joined
    assert COMPARISON_FORMAT_HINT in joined
    assert "No ## headings" not in joined


def test_compact_chart_turn_uses_vega_fence_not_plain_prose():
    from app.modules.chat.prompt_constants import CHART_FORMAT_HINT

    parts = _style_format_hints(
        query_text=(
            "Make a bar chart of average monthly rainfall in Seattle: "
            "Jan 5.7, Feb 3.5, Mar 3.7, Apr 2.4, May 1.8, Jun 1.5 inches."
        ),
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CHART_FORMAT_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    joined = "\n".join(parts)
    assert CHART_FORMAT_HINT in joined
    assert "NEVER substitute a markdown table" in joined
    assert CHART_FORMAT_HINT in joined
    assert "no leftover" in joined.lower() or "leftover bare numbers" in joined
    assert CHART_FORMAT_HINT in joined
    assert "sample data" in joined
    assert "ask ONE question for the values" in joined
    assert "No ## headings" not in joined


def test_compact_mermaid_turn_uses_flowchart_fence_not_plain_prose():
    from app.modules.chat.prompt_constants import MERMAID_FORMAT_HINT

    parts = _style_format_hints(
        query_text=(
            "Draw a mermaid flowchart of making a cup of coffee, "
            "from grinding beans to drinking. Keep it to about 8 steps."
        ),
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert MERMAID_FORMAT_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    joined = "\n".join(parts)
    assert "joke setup" in joined
    assert "Do not interview for steps" in joined
    assert MERMAID_FORMAT_HINT in joined
    assert "No ## headings" not in joined


def test_compact_tips_turn_uses_callout_blockquotes_not_plain_prose():
    from app.modules.chat.prompt_constants import CALLOUT_FORMAT_HINT

    parts = _style_format_hints(
        query_text=(
            "Give me 3 tips for staying focused while studying. "
            "Include a warning about all-nighters."
        ),
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CALLOUT_FORMAT_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    joined = "\n".join(parts)
    assert "> Tip:" not in joined
    assert "> Warning:" in joined
    assert "> Note:" in joined
    assert "Never for hints" in joined
    assert "No ## headings" not in joined


def test_compact_week_plan_uses_detailed_learning_plan_not_plain_prose():
    from app.modules.chat.prompt_constants import LEARNING_PLAN_HINT

    parts = _style_format_hints(
        query_text="Give me a 4-week plan to learn Spanish for travel.",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert LEARNING_PLAN_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    joined = "\n".join(parts)
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert "No ## headings" not in joined


def test_compact_spanish_week_plan_uses_detailed_learning_plan():
    from app.modules.chat.prompt_constants import LEARNING_PLAN_HINT
    from app.modules.turn_reading.format import is_howto_question
    from app.modules.turn_reading.teaching import is_learning_plan_request

    query = "Dame un plan de 4 semanas para aprender español"
    assert is_howto_question(query)
    assert is_learning_plan_request(query)
    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert LEARNING_PLAN_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts


def test_day_plan_still_uses_richer_format_hint():
    parts = _style_format_hints(
        query_text="plan my day",
        is_day_plan=True,
        minimal_personal_context=False,
    )
    assert FORMAT_CONTRACT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts


def test_fragment_gets_writing_line_hint():
    assert is_bare_writing_line("Whoever made the best decision for me")
    assert is_bare_writing_line("Because I said so yesterday")
    assert is_bare_writing_line("correct this sentence: I goes to store")
    assert is_bare_writing_line("Please help me proofread this paragraph")
    assert is_bare_writing_line("I want you to proofread this paragraph")
    assert not is_bare_writing_line("What is 2+2?")
    assert not is_bare_writing_line("What does proofread mean?")
    assert not is_bare_writing_line("Tell me about mitochondria")
    assert not is_bare_writing_line("Python vs Java")

    parts = _style_format_hints(
        query_text="Whoever made the best decision for me",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert WRITING_LINE_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT in parts
    assert "Do not say you are an AI" in WRITING_LINE_HINT


def test_yes_follow_through_hint_is_not_a_greeting():
    from app.modules.chat.prompt_constants import CONFIRM_FOLLOW_THROUGH_HINT

    parts = _style_format_hints(
        query_text="yes",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CONFIRM_FOLLOW_THROUGH_HINT in parts
    assert "Carry out that offer" in CONFIRM_FOLLOW_THROUGH_HINT


def test_yes_confirms_what_the_last_reply_asked_to_confirm():
    # Live (2026-10-25): "Could you confirm both figures?", "Yes", and it asked again.
    from app.modules.chat.prompt_constants.conversation import CONFIRMED_HINT

    for query in ("yes", "Yes.", "yep", "sure"):
        parts = _style_format_hints(
            query_text=query, is_day_plan=False, minimal_personal_context=False, compact=True
        )
        assert CONFIRMED_HINT in parts
    parts = _style_format_hints(
        query_text="y", is_day_plan=False, minimal_personal_context=False, compact=True
    )
    assert CONFIRMED_HINT not in parts


def test_bare_y_does_not_invent_an_offer_to_follow_through_on():
    from app.modules.chat.prompt_constants import CONFIRM_FOLLOW_THROUGH_HINT

    parts = _style_format_hints(
        query_text="y",
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert CONFIRM_FOLLOW_THROUGH_HINT not in parts


def test_clarification_hint_asks_once_when_purpose_or_data_missing():
    from app.modules.chat.prompt_constants import CLARIFICATION_HINT
    from app.modules.chat.prompt_constants.writing import EMAIL_ASK_PURPOSE_HINT, EMAIL_DRAFT_HINT
    from app.modules.turn_reading.writing_purpose import is_underspecified_writing_request

    assert "escribeme un correo" in CLARIFICATION_HINT
    assert "LinkedIn" in CLARIFICATION_HINT
    assert "caption" in CLARIFICATION_HINT
    assert "ask ONE question for that purpose" in CLARIFICATION_HINT
    assert "ask ONE question for the values" in CLARIFICATION_HINT
    assert "Do not interview for steps" in CLARIFICATION_HINT
    assert "Function plots" in CLARIFICATION_HINT
    assert "Python" in CLARIFICATION_HINT
    assert is_underspecified_writing_request("write me an email")
    assert is_underspecified_writing_request("escribeme un correo")
    assert not is_underspecified_writing_request("email my boss about PTO")
    assert not is_underspecified_writing_request("write an email saying I will be late")
    assert "named a recipient" not in EMAIL_DRAFT_HINT
    assert "escribeme un correo" in EMAIL_ASK_PURPOSE_HINT


def test_writing_request_kinds_cover_each_output_shape():
    from app.modules.turn_reading.writing_kind import writing_request_kind

    cases = {
        "Write me an email about taking Friday off": "email",
        "Message my friend saying happy birthday": "message",
        "Write a LinkedIn post announcing my new role": "social",
        "Write me a facebook post updating about my healing": "social",
        "Write me a linkedin update post about my new job": "social",
        "Write a short LinkedIn post comparing Python and Java": "social",
        "Rewrite my LinkedIn post": "social",
        "Translate 'see you tomorrow' into Spanish": "translation",
        "Translation: 'see you tomorrow' into Spanish": "translation",
        "Could you help me translate this into Spanish?": "translation",
        "Please, translate this": "translation",
        "Por favor, traduce esto al inglés": "translation",
        "翻译这句话": "translation",
        "翻译这篇文章": "translation",
        "翻译这句话：Hello world": "translation",
        "翻译这段文字“Hello world”": "translation",
        "翻译这句话成英文：Bonjour": "translation",
        "翻译：为什么这么难": "translation",
        "翻訳してください": "translation",
        "翻訳して": "translation",
        "訳してください": "translation",
        "訳して ください": "translation",
        "번역해 주세요": "translation",
        "번역해주세요": "translation",
        "번역 부탁드립니다": "translation",
        "번역 좀 해주세요": "translation",
        "번역 좀 부탁해 주세요": "translation",
        "翻译理论是什么？": None,
        "翻译文章需要注意什么？": None,
        "翻譯文章需要注意什麼？": None,
        "翻译这篇文章需要注意什么？": None,
        "翻译这句话为什么这么难？": None,
        "翻译这句话为何如此困难？": None,
        "翻译这篇文章成英文需要注意什么？": None,
        "翻译为什么这么难？": None,
        "翻譯為什麼這麼難？": None,
        "翻译为何这么难？": None,
        "翻訳とは何ですか？": None,
        "翻訳している人は誰ですか？": None,
        "翻訳して いる人は誰ですか？": None,
        "번역이란 무엇인가요?": None,
        "번역하는 방법은 무엇인가요?": None,
        "번역해 주는 사람은 누구예요?": None,
        'Translate "write me an email" into Spanish': "translation",
        "Write one paragraph about photosynthesis": "prose",
        "Now write a short cover letter for the best one": "prose",
        "Draft a resume for a software role": "prose",
        "Write a short article comparing Python and Java": "prose",
        "Write a 500-word essay": "prose",
        "Is this sentence correct?": "edit",
        "Please help me proofread this paragraph": "edit",
        "I want you to proofread this paragraph": "edit",
        "How do I delete a LinkedIn post?": None,
        "How do I write a LinkedIn post?": None,
        (
            "How do I make it concise? Please write a LinkedIn post comparing Python and Java."
        ): "social",
        (
            "How do I revise 'This is good. Really good'? Please translate it into French."
        ): "translation",
        (
            "How do I shorten this, e.g. for LinkedIn? Please write a LinkedIn post about it."
        ): "social",
        ('How do I improve this prompt? It says "Write a LinkedIn post about AI."'): None,
        "How do I improve this sentence? Then proofread it.": "edit",
        'How do I revise it? It says "Translate this into French."': None,
        (
            "How do I revise 'I don't know. Please help'? Please translate it into French."
        ): "translation",
        (
            "How do I revise ‘I don’t know. Please help’? Please translate it into French."
        ): "translation",
        ("How do I revise 'the students' essays. Please proofread them.'?"): None,
        ("How do I revise 'these words' if I don't like them? Please proofread it."): "edit",
        "How do I end a list with etc. Then proofread it.": "edit",
        'How do I respond to "Can you attend?" Please write a reply.': "message",
        "How do I improve Chris' sentence? Please proofread it.": "edit",
        ("How do I improve this email? It is for my boss. Please rewrite it."): "edit",
        ("How do I improve this? Please proofread it before I email my boss."): "edit",
        ("How do I improve this prompt (current text: Be concise. Write an email.)?"): None,
        ('How do I improve this prompt (example: "Be concise." Write an email.)?'): None,
        ('How do I improve this? Check the phrase "write an email."'): None,
        ('How do I improve this? Create a prompt saying "write an email."'): None,
        ('How do I improve this prompt? It says "escribe un correo sobre vacaciones."'): None,
        ("How do I revise 'these words' in the phrase 'Be concise.'? Please proofread it."): "edit",
        ("How do I improve this prompt? It gives an example, e.g. Write an email."): None,
        ('How do I improve this? Write a LinkedIn post quoting "escribe un correo".'): "social",
        ("How do I revise 'the students' and teachers' essays. Please proofread them.'?"): None,
        "Please write a reply before I email my boss.": "message",
        "Explain translation in protein synthesis": None,
        "Explain how ribosomes translate mRNA": None,
        "What is grammar?": None,
        "What does proofread mean?": None,
        "What is the capital of Kenya?": None,
    }
    for query, expected in cases.items():
        assert writing_request_kind(query) == expected


def test_bare_drafts_ask_once_but_supplied_purpose_drafts_now():
    from app.modules.turn_reading.writing_purpose import is_underspecified_writing_request

    assert is_underspecified_writing_request("Message to my friend")
    assert is_underspecified_writing_request("write me an email")
    assert is_underspecified_writing_request("escribeme un correo")
    assert not is_underspecified_writing_request("Message my friend saying happy birthday")
    assert not is_underspecified_writing_request("write a vacation email to my boss")
    assert not is_underspecified_writing_request("escribeme un correo diciendo que llegare tarde")


def test_each_writing_kind_gets_only_its_relevant_format_hint():
    from app.modules.chat.prompt_constants import WRITING_LINE_HINT
    from app.modules.chat.prompt_constants.writing import (
        EMAIL_ASK_PURPOSE_HINT,
        EMAIL_DRAFT_HINT,
        PERSONAL_RECORD_HINT,
        PROSE_WRITING_HINT,
        SOCIAL_DRAFT_HINT,
        TRANSLATION_FORMAT_HINT,
    )

    cases = (
        ("Message to my friend", EMAIL_ASK_PURPOSE_HINT),
        ("Message my friend saying happy birthday", EMAIL_DRAFT_HINT),
        ("Write a LinkedIn post announcing my new role", SOCIAL_DRAFT_HINT),
        ("Write me a facebook post updating about my healing", SOCIAL_DRAFT_HINT),
        ("Translate 'see you tomorrow' into Spanish", TRANSLATION_FORMAT_HINT),
        ("Write one paragraph about photosynthesis", PROSE_WRITING_HINT),
        ("Now write a short cover letter for the best one", PERSONAL_RECORD_HINT),
        ("Is this sentence correct?", WRITING_LINE_HINT),
    )
    specialized = {
        EMAIL_ASK_PURPOSE_HINT,
        EMAIL_DRAFT_HINT,
        PERSONAL_RECORD_HINT,
        PROSE_WRITING_HINT,
        SOCIAL_DRAFT_HINT,
        TRANSLATION_FORMAT_HINT,
        WRITING_LINE_HINT,
    }
    for query, expected in cases:
        parts = _style_format_hints(
            query_text=query,
            is_day_plan=False,
            minimal_personal_context=False,
            compact=True,
        )
        assert expected in parts
        assert specialized.intersection(parts) == {expected}


_COPY_FENCE_INSTRUCTION = "put ONLY the final send-ready wording inside a fenced code block"


def _writing_style_parts(query: str, *, compact: bool = False) -> list[str]:
    return _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=compact,
    )


def test_writing_kinds_displace_competing_format_contracts():
    from app.modules.chat.prompt_constants import SHORT_RESPONSE_FORMAT_HINT
    from app.modules.chat.prompt_constants.writing import (
        EMAIL_DRAFT_HINT,
        PROSE_WRITING_HINT,
        SOCIAL_DRAFT_HINT,
        TRANSLATION_FORMAT_HINT,
    )

    cases = (
        ("email my boss about PTO", EMAIL_DRAFT_HINT, False),
        ("Write a LinkedIn post announcing my new role", SOCIAL_DRAFT_HINT, False),
        ("Translate 'see you tomorrow' into Spanish", TRANSLATION_FORMAT_HINT, True),
        ("Write one paragraph about photosynthesis", PROSE_WRITING_HINT, True),
        ("Write a short article comparing Python and Java", PROSE_WRITING_HINT, True),
    )
    competing = {
        COMPACT_RESPONSE_FORMAT_HINT,
        FORMAT_CONTRACT,
        SHORT_RESPONSE_FORMAT_HINT,
    }
    for query, expected, skip_copy_fence in cases:
        for compact in (False, True):
            parts = _writing_style_parts(query, compact=compact)
            assert expected in parts
            assert not competing.intersection(parts)
            joined = "\n".join(parts)
            if skip_copy_fence:
                assert _COPY_FENCE_INSTRUCTION not in joined
            else:
                assert _COPY_FENCE_INSTRUCTION in joined


def test_writing_deliverable_wins_over_incidental_comparison_layout():
    from app.modules.chat.prompt_constants import COMPARISON_FORMAT_HINT
    from app.modules.chat.prompt_constants.writing import PROSE_WRITING_HINT, SOCIAL_DRAFT_HINT

    article = _style_format_hints(
        query_text="Write an article comparing Python vs Java",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert PROSE_WRITING_HINT in article
    assert COMPARISON_FORMAT_HINT not in article

    modified_article = _style_format_hints(
        query_text="Write a short article comparing Python and Java",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert PROSE_WRITING_HINT in modified_article
    assert COMPARISON_FORMAT_HINT not in modified_article

    post = _style_format_hints(
        query_text="Write a LinkedIn post comparing Python vs Java",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert SOCIAL_DRAFT_HINT in post
    assert COMPARISON_FORMAT_HINT not in post

    modified_post = _style_format_hints(
        query_text="Write a short LinkedIn post comparing Python and Java",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert SOCIAL_DRAFT_HINT in modified_post
    assert COMPARISON_FORMAT_HINT not in modified_post


def test_informational_queries_do_not_receive_writing_hints():
    from app.modules.chat.prompt_constants import WRITING_LINE_HINT
    from app.modules.chat.prompt_constants.writing import (
        EMAIL_ASK_PURPOSE_HINT,
        SOCIAL_DRAFT_HINT,
        TRANSLATION_FORMAT_HINT,
    )

    writing_hints = {
        EMAIL_ASK_PURPOSE_HINT,
        SOCIAL_DRAFT_HINT,
        TRANSLATION_FORMAT_HINT,
        WRITING_LINE_HINT,
    }
    for query in (
        "How do I delete a LinkedIn post?",
        "How do I write a LinkedIn post?",
        "Explain translation in protein synthesis",
        "Explain how ribosomes translate mRNA",
        "What is grammar?",
        "What does proofread mean?",
    ):
        parts = _style_format_hints(
            query_text=query,
            is_day_plan=False,
            minimal_personal_context=False,
            compact=True,
        )
        assert not writing_hints.intersection(parts)


def test_explicit_table_request_survives_short_and_compact_styles():
    from app.modules.chat.prompt_constants import (
        COMPACT_RESPONSE_FORMAT_HINT,
        SHORT_RESPONSE_FORMAT_HINT,
        UNIVERSAL_FORMAT_BASELINE,
    )

    assert "unless the user explicitly requested one" in SHORT_RESPONSE_FORMAT_HINT
    assert "explicitly asked for a table" in COMPACT_RESPONSE_FORMAT_HINT
    assert "Honor an explicit request for a table" in UNIVERSAL_FORMAT_BASELINE


def test_translation_and_proofreading_do_not_load_private_rich_context():
    from app.modules.turn_reading.personal import needs_rich_context

    assert not needs_rich_context("Translate 'hello' into Spanish")
    assert not needs_rich_context("Is this sentence correct?")
    assert needs_rich_context("Message my wife saying I will be late")


def test_universal_baseline_bans_invented_tables_and_hooks():
    assert "Never invent a pipe table" in UNIVERSAL_FORMAT_BASELINE
    assert "timetables" in UNIVERSAL_FORMAT_BASELINE
    assert "Ah, the eternal question" in UNIVERSAL_FORMAT_BASELINE
    assert "word choice only" in TONE_FORMAT_GUARD
    assert "quotation ask" in TONE_FORMAT_GUARD
    assert "one sentence" in TONE_FORMAT_GUARD
    assert "casual preference" in TONE_FORMAT_GUARD


def test_compact_quote_turn_uses_blockquote_not_plain_prose():
    from app.modules.chat.prompt_constants import COMPACT_RESPONSE_FORMAT_HINT, QUOTE_FORMAT_HINT
    from app.modules.turn_reading.format import is_quote_question

    query = "Give me a famous quote by Maya Angelou about courage, with attribution."
    assert is_quote_question(query)
    assert not is_quote_question("What's the latest stock quote for AAPL?")
    assert not is_quote_question("Compare Python vs Java")

    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=True,
    )
    assert QUOTE_FORMAT_HINT in parts
    assert COMPACT_RESPONSE_FORMAT_HINT not in parts
    joined = "\n".join(parts)
    assert QUOTE_FORMAT_HINT in joined
    assert "No ## headings" not in joined


@pytest.mark.parametrize(
    "text, expected",
    [
        ("What can you help me with? Give a few concrete examples.", True),
        ("What can you do?", True),
        ("How can you help me?", True),
        ("¿En qué puedes ayudarme? Dame algunos ejemplos concretos.", True),
        ("En quoi peux-tu m'aider ? Donne quelques exemples concrets.", True),
        ("What can you help me with on this FastAPI bug?", False),
        ("Can you help me with Python?", False),
        ("Write me an email about taking Friday off", False),
        ("Who am I?", False),
    ],
)
def test_is_capabilities_question(text, expected):
    from app.modules.turn_reading.capabilities import is_capabilities_question
    from app.modules.turn_reading.writing_kind import (
        is_email_or_message_request,
        writing_request_kind,
    )

    assert is_capabilities_question(text) is expected
    if expected:
        assert writing_request_kind(text) is None
        assert not is_email_or_message_request(text)


def test_capabilities_overview_skips_email_draft_contract():
    from app.modules.chat.prompt_constants import (
        CAPABILITIES_FORMAT_HINT,
        CLARIFICATION_HINT,
        COPY_DELIVERABLE_HINT,
        FORMAT_CONTRACT,
    )
    from app.modules.chat.prompt_constants.writing import EMAIL_DRAFT_HINT
    from app.modules.turn_reading.capabilities import is_capabilities_question

    query = "What can you help me with? Give a few concrete examples."
    assert is_capabilities_question(query)
    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=False,
    )
    assert CAPABILITIES_FORMAT_HINT in parts
    assert FORMAT_CONTRACT not in parts
    assert COPY_DELIVERABLE_HINT not in parts
    assert EMAIL_DRAFT_HINT not in parts
    assert CLARIFICATION_HINT not in parts
    joined = "\n".join(parts)
    assert CAPABILITIES_FORMAT_HINT in joined
    assert "No ## headings" in joined
    assert FORMAT_CONTRACT not in joined


@pytest.mark.parametrize(
    "query",
    [
        "I work at Uber but I want to change to Google",
        "I work at Uber and Google is my next goal",
        "My current employer is Uber; I may apply to Google",
        "I am thinking about leaving Uber for Google",
        "Google looks interesting, but I still work at Uber",
    ],
)
def test_career_updates_are_conversation_not_unsolicited_email_drafts(query):
    from app.modules.chat.prompt_constants import NON_DRAFT_TURN_HINT
    from app.modules.chat.prompt_constants.writing import EMAIL_DRAFT_HINT
    from app.modules.chat.prompt_format import _style_format_hints
    from app.modules.turn_reading.writing_kind import (
        is_email_or_message_request,
        writing_request_kind,
    )

    assert writing_request_kind(query) is None
    assert not is_email_or_message_request(query)
    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert NON_DRAFT_TURN_HINT in parts
    assert EMAIL_DRAFT_HINT not in parts


def test_explicit_google_outreach_request_still_gets_email_draft_contract():
    from app.modules.chat.prompt_constants import NON_DRAFT_TURN_HINT
    from app.modules.chat.prompt_constants.writing import EMAIL_DRAFT_HINT
    from app.modules.chat.prompt_format import _style_format_hints

    parts = _style_format_hints(
        query_text="Write an email to a Google recruiter about my software engineering experience",
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert EMAIL_DRAFT_HINT in parts
    assert NON_DRAFT_TURN_HINT not in parts


def test_plain_career_disclosure_gets_short_conversation_contract():
    from app.modules.chat.prompt_constants import (
        COPY_DELIVERABLE_HINT,
        FORMAT_CONTRACT,
        PERSONAL_DISCLOSURE_HINT,
        SHORT_RESPONSE_FORMAT_HINT,
    )
    from app.modules.chat.prompt_format import _style_format_hints
    from app.modules.turn_reading.personal import is_personal_disclosure_turn

    query = "I work at Uber but I want to change to Google"
    assert is_personal_disclosure_turn(query)
    parts = _style_format_hints(
        query_text=query,
        is_day_plan=False,
        minimal_personal_context=False,
    )
    assert PERSONAL_DISCLOSURE_HINT in parts
    assert "entire reply" in PERSONAL_DISCLOSURE_HINT
    assert "no heading, list, steps, or action plan" in PERSONAL_DISCLOSURE_HINT
    assert "currently at X; considering Y" in PERSONAL_DISCLOSURE_HINT
    assert SHORT_RESPONSE_FORMAT_HINT in parts
    assert FORMAT_CONTRACT not in parts
    assert COPY_DELIVERABLE_HINT not in parts


@pytest.mark.parametrize(
    "query",
    [
        "I work at Uber. What skills should I build for Google?",
        "I work at Uber; can you compare it with Google?",
        "My goal is Google—help me make a plan",
        "I work at Uber, search for current Google roles",
        "I work at Uber. Write an email to a Google recruiter",
        "I work at Uber; make me a transition plan",
        "Should I leave Uber for Google?",
        # A topic they are stuck on asks to be taught.
        "I'm confused about pointers in C",
        "I’m lost with derivatives",
    ],
)
def test_personal_context_with_a_real_request_is_not_only_a_disclosure(query):
    from app.modules.turn_reading.personal import is_personal_disclosure_turn

    assert not is_personal_disclosure_turn(query)


@pytest.mark.parametrize(
    "query",
    [
        "We need a hotel in Paris",
        "Our team needs current API pricing",
        "We are looking for a restaurant nearby",
        "Our company wants the latest tax guidance",
    ],
)
def test_collective_implicit_requests_are_not_personal_disclosures(query):
    from app.modules.turn_reading.personal import is_personal_disclosure_turn

    assert not is_personal_disclosure_turn(query)


@pytest.mark.parametrize("query", ["We moved to Boston", "We work in healthcare"])
def test_collective_personal_facts_remain_disclosures(query):
    from app.modules.turn_reading.personal import is_personal_disclosure_turn

    assert is_personal_disclosure_turn(query)
