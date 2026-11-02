from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.context_window import estimate_tokens
from app.modules.chat.prompt_builder import PromptStats, build_prompt_messages
from app.modules.chat.prompt_constants.capabilities import CAPABILITIES_FORMAT_HINT
from app.modules.chat.prompt_constants.chart import CHART_FORMAT_HINT
from app.modules.chat.prompt_constants.diagrams import MERMAID_FORMAT_HINT
from app.modules.chat.prompt_constants.format import (
    COMPARISON_FORMAT_HINT,
    FORMAT_CONTRACT,
)
from app.modules.chat.prompt_constants.privacy import (
    ADVICE_PERSONALIZE_HINT,
    BROAD_SELF_ANSWER_HINT,
    CLARIFICATION_HINT,
    EXAMPLE_PERSONALIZE_HINT,
    PRIVACY_HINT,
)
from app.modules.chat.prompt_constants.routing import LIGHTWEIGHT_REPLY_HINT
from app.modules.chat.prompt_constants.writing import EMAIL_DRAFT_HINT
from app.modules.chat.prompt_profile import (
    format_user_name_only_block,
    format_user_profile_block,
    should_include_profile_email,
)
from app.modules.chat.turn_prep import resolve_client_geo
from app.modules.chemistry.reply_policy import CHEMISTRY_FENCE_HINT
from app.modules.conversation import chats_repository, messages_repository
from app.modules.turn_reading.personal import is_personal_advice_question, needs_rich_context
from app.modules.turn_reading.routing import is_broad_self_question, is_lightweight_chat_turn
from app.modules.turn_reading.writing_kind import is_writing_deliverable_request
from app.services.locale import locale_system_hint
from app.tests.fakes import FakeSessionCM, make_user
from app.tests.modules.chat.chat_test_support import system_prompt


def test_resolve_client_geo_ignores_client_when_location_disabled():
    user = MagicMock()
    user.location_enabled = False
    user.location = "Oakland, CA"
    geo = resolve_client_geo(
        user,
        "Where am I",
        client_location="San Francisco, CA",
        client_latitude=37.7,
        client_longitude=-122.4,
    )
    assert geo.user_location is None
    assert geo.client_lat is None
    assert geo.client_lng is None
    assert geo.has_geo_fix is False


def test_resolve_client_geo_uses_client_when_location_enabled():
    user = MagicMock()
    user.location_enabled = True
    user.location = "Oakland, CA"
    geo = resolve_client_geo(
        user,
        "Where am I",
        client_location="Berkeley, CA",
        client_latitude=37.87,
        client_longitude=-122.27,
    )
    assert geo.user_location == "Berkeley, CA"
    assert geo.client_lat == 37.87
    assert geo.client_lng == -122.27
    assert geo.has_geo_fix is True


def test_estimate_tokens_minimum():
    assert estimate_tokens("") == 1
    assert estimate_tokens("hello") == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Send me an email to my wife", True),
        ("email my boss about PTO", True),
        ("escribeme un correo", True),
        ("what is Python", False),
    ],
)
def test_is_writing_deliverable_request(text: str, expected: bool):
    assert is_writing_deliverable_request(text) is expected


@pytest.mark.asyncio
async def test_build_prompt_includes_email_draft_hint_for_email_request():
    user = MagicMock()
    user.id = uuid4()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False),
            query_text="Send an email to my wife about PTO",
        )

    system = system_prompt(messages)
    assert EMAIL_DRAFT_HINT in system
    assert "cannot send email or SMS" in system.lower() or "Never say you sent" in system
    assert EMAIL_DRAFT_HINT in system


@pytest.mark.asyncio
async def test_build_prompt_includes_comparison_table_hint():
    user = MagicMock()
    user.id = uuid4()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False),
            query_text="Python vs java",
        )

    system = system_prompt(messages)
    # Technical compares get a table plus code only where it adds information.
    assert COMPARISON_FORMAT_HINT in system
    assert COMPARISON_FORMAT_HINT in system
    assert "only when" in system
    assert "pipe table" in system.lower()
    assert "NEVER put source code" in system
    assert "### headings" in system


@pytest.mark.asyncio
async def test_build_prompt_includes_chart_vega_hint():
    user = MagicMock()
    user.id = uuid4()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False),
            query_text=(
                "Make a bar chart of average monthly rainfall in Seattle: "
                "Jan 5.7, Feb 3.5, Mar 3.7, Apr 2.4, May 1.8, Jun 1.5 inches."
            ),
        )

    system = system_prompt(messages)
    assert CHART_FORMAT_HINT in system
    assert "```chart" in system
    assert CHART_FORMAT_HINT in system
    assert "NEVER substitute a markdown table" in system
    assert "No ## headings" not in system


@pytest.mark.asyncio
async def test_build_prompt_includes_mermaid_layout_hint():
    user = MagicMock()
    user.id = uuid4()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False),
            query_text=(
                "Draw a mermaid flowchart of making a cup of coffee, "
                "from grinding beans to drinking. Keep it to about 8 steps."
            ),
        )

    system = system_prompt(messages)
    assert MERMAID_FORMAT_HINT in system
    assert "```mermaid" in system
    assert "joke setup" in system
    assert "No ## headings" not in system


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Python vs java", True),
        ("python versus Java", True),
        ("compare React and Vue", True),
        ("difference between SQL and NoSQL", True),
        ("which is better, Go or Rust?", True),
        ("tell me about Python", False),
        ("Give me tips on how to master python", False),
        ("roadmap to learn TypeScript", False),
        ("hi", False),
        ("", False),
    ],
)
def test_is_comparison_question(text, expected):
    from app.modules.turn_reading.format import is_comparison_question

    assert is_comparison_question(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Make a bar chart of average monthly rainfall in Seattle: Jan 5.7, Feb 3.5, Mar 3.7, Apr 2.4, May 1.8, Jun 1.5 inches.",
            True,
        ),
        ("draw a line chart of my scores", True),
        ("pie chart of market share", True),
        ("make a bar chart of monthly rainfall", True),
        # A plot of data named by its kind.
        (
            "Plot this experiment as a scatter plot with a best-fit line: "
            "x = 1,2,3,4,5 and y = 2.1,3.9,6.2,7.8,10.1",
            True,
        ),
        ("scatterplot of study hours vs score: 1 50, 2 60, 3 70", True),
        ("make a bar graph of my grades: math 90, art 75", True),
        ("make a line graph of my monthly sales: jan 10, feb 12, mar 9", True),
        ("Make a histogram of these test scores: 55, 62, 68, 70", True),
        # A curve is maths' graph, and a definition is not a request.
        ("draw the line graph of y = 2x+1", False),
        ("plot f(x) = x^2 as a line graph", False),
        ("graph y = x^2", False),
        ("what is a scatter plot?", False),
        ("What's a line graph", False),
        ("Draw a mermaid flowchart of making coffee", False),
        ("Make a flowchart of user login", False),
        ("Compare Python vs Java", False),
        ("tell me about rainfall in Seattle", False),
        ("What is a bar chart?", False),
        ("Do not make a bar chart; explain the numbers.", False),
        ("", False),
    ],
)
def test_is_chart_question(text, expected):
    from app.modules.turn_reading.chart import is_chart_question

    assert is_chart_question(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Draw a mermaid flowchart of making a cup of coffee, from grinding beans to drinking. Keep it to about 8 steps.",
            True,
        ),
        ("flowchart of user login", True),
        ("flowchart of making coffee", True),
        ("sequence diagram of HTTP request", True),
        ("show this as mermaid", True),
        ("compare mermaid vs plantuml", False),
        ("what is mermaid", False),
        ("draw a triangle", False),
        ("Show the molecular structure of ethanol", False),
        ("", False),
    ],
)
def test_is_mermaid_question(text, expected):
    from app.modules.turn_reading.diagrams import is_mermaid_question

    assert is_mermaid_question(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "Give me 3 tips for staying focused while studying. Include a warning about all-nighters.",
            True,
        ),
        ("Give me tips on how to master python", False),
        ("study tips for finals", False),
        ("include a warning about all-nighters", True),
        ("warning about all-nighters", True),
        ("roadmap to learn TypeScript", False),
        ("How do I make a cup of coffee", False),
        ("Compare Python vs Java", False),
        ("tip of the iceberg", False),
        ("leave a tip", False),
        ("", False),
    ],
)
def test_is_callout_question(text, expected):
    from app.modules.turn_reading.format import is_callout_question

    assert is_callout_question(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Give me a 4-week plan to learn Spanish for travel.", True),
        ("roadmap to learn TypeScript", True),
        ("How do I set up a React Native project from scratch?", True),
        ("week-by-week study plan for the SAT", True),
        ("Dame un plan de 4 semanas para aprender español", True),
        ("Comment faire un plan de 8 semaines", True),
        ("Wie mache ich einen 4-Wochen-Plan", True),
        ("plan my day", False),
        ("hace 3 semanas fui a Madrid", False),
        ("Give me 3 tips for staying focused while studying.", False),
        ("Compare Python vs Java", False),
        ("Make a bar chart of rainfall", False),
        ("How do I say hello in Spanish?", False),
        ("", False),
    ],
)
def test_is_howto_question(text, expected):
    from app.modules.turn_reading.format import is_howto_question

    assert is_howto_question(text) is expected


def test_format_hints_discourage_tables_for_how_tos():
    from app.modules.chat.prompt_constants import FORMAT_CONTRACT

    blob = FORMAT_CONTRACT
    assert "roadmap" in blob.lower() or "how-to" in blob.lower()
    assert "NEVER" in blob or "Never" in blob
    assert "pipe table" in blob.lower() or "pipe tables" in blob.lower()
    assert FORMAT_CONTRACT in blob
    assert FORMAT_CONTRACT in blob
    assert "ask one question" in blob.lower()
    assert "invent a generic letter" in blob.lower()


def test_universal_format_baseline_pins_answer_first_and_no_decoration():
    """Balanced/detailed turns must stay answer-first and skip decorative
    headings, emoji, raw URLs, and restating the question. These live in
    UNIVERSAL_FORMAT_BASELINE so they cannot silently drop from the prompt."""
    from app.modules.chat.prompt_constants import (
        STYLE_HINTS,
        UNIVERSAL_FORMAT_BASELINE,
    )

    assert (
        "Lead with the answer (a calculation leads with its working); explanation after."
        in UNIVERSAL_FORMAT_BASELINE
    )
    assert "No intro paragraph before the conclusion." in UNIVERSAL_FORMAT_BASELINE
    assert "Never use decorative headings" in UNIVERSAL_FORMAT_BASELINE
    assert "Introduction, Background, Overview, Conclusion" in UNIVERSAL_FORMAT_BASELINE
    assert "Let's dive in" in UNIVERSAL_FORMAT_BASELINE
    # Emoji follow the user's setting (``response_tone.emoji_hint``), not a baseline ban.
    assert "emoji" not in UNIVERSAL_FORMAT_BASELINE.lower()
    assert "[OpenAI docs](url)" in UNIVERSAL_FORMAT_BASELINE
    assert "not raw URLs" in UNIVERSAL_FORMAT_BASELINE
    assert "Do not restate the question." in UNIVERSAL_FORMAT_BASELINE
    assert "simplest structure" in UNIVERSAL_FORMAT_BASELINE
    assert "do not add sections just to look structured" in UNIVERSAL_FORMAT_BASELINE
    assert (
        "Lead with the answer (a calculation leads with its working); explanation after."
        in STYLE_HINTS["balanced"]
    )


def test_format_contract_is_markdown_not_ui_fences():
    """The model writes Markdown. Teaching ```tip / ```steps / ```smiles on
    every rich turn made it invent cards (music → molecule). Renderers still
    accept those fences on old messages."""
    from app.modules.chat.prompt_constants import (
        FORMAT_CONTRACT,
        VISUALIZATION_HINTS,
    )

    assert "```tip" not in FORMAT_CONTRACT
    assert "```steps" not in FORMAT_CONTRACT
    assert "```comparison" not in FORMAT_CONTRACT
    assert "```details" not in FORMAT_CONTRACT
    assert "```answer" not in FORMAT_CONTRACT
    assert "A `>` quote card is only a cited quotation whose last line is " in FORMAT_CONTRACT
    assert "`— Name`" in FORMAT_CONTRACT
    assert "> Warning:" in FORMAT_CONTRACT
    assert "> Note:" in FORMAT_CONTRACT
    assert "Tip:" not in FORMAT_CONTRACT
    assert "quoted italic paragraph" in FORMAT_CONTRACT
    assert "```email" in FORMAT_CONTRACT
    assert "```python" in FORMAT_CONTRACT
    assert 'name = "john"' in FORMAT_CONTRACT
    assert "An untagged fence has no language label" in FORMAT_CONTRACT
    assert "Do not backtick a phrase" in FORMAT_CONTRACT
    assert "$O(n)$" in FORMAT_CONTRACT
    assert "Bullets are for parallel unordered items" in FORMAT_CONTRACT
    assert "Numbers are for steps, rankings" in FORMAT_CONTRACT
    # "Ways to become rich": numbered items, each led by a bold label.
    assert "**bold label of 2-5 words**" in FORMAT_CONTRACT
    assert "The bold labels alone give the gist" in FORMAT_CONTRACT
    assert "Letters are for alternatives/answer choices" in FORMAT_CONTRACT
    assert "roman numerals only when requested" in FORMAT_CONTRACT
    assert "Nest at most one level" in FORMAT_CONTRACT
    assert "unordered children stay bullets" in FORMAT_CONTRACT
    assert "plain labels such as `A.` or `I.`" in FORMAT_CONTRACT
    assert "```smiles" not in VISUALIZATION_HINTS
    assert CHEMISTRY_FENCE_HINT not in VISUALIZATION_HINTS
    from app.modules.math.reply_policy import MATH_SOLVER_HINT

    assert "```smiles" in CHEMISTRY_FENCE_HINT
    assert "Do not emit ```molecule3d" in CHEMISTRY_FENCE_HINT
    assert "```smiles" not in MATH_SOLVER_HINT

    from app.modules.chemistry.reply_policy import attach_chemistry_fence_hint

    pubchem = "[Chemistry context]\nCanonical SMILES: CCO"
    assert attach_chemistry_fence_hint(pubchem).startswith(CHEMISTRY_FENCE_HINT)
    assert attach_chemistry_fence_hint("[Verified pH calculation]\n7") == (
        "[Verified pH calculation]\n7"
    )


def test_math_formula_shape_rule_is_unified():
    """Global hints and math-solver hints must agree: inline $ for steps,
    ```math only for standalone display — not contradictory guidance."""
    from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_REPLY_POLICY, MATH_SOLVER_HINT

    for blob in (MATH_INTENT_HINT, MATH_SOLVER_HINT):
        assert "inline" in blob.lower()
        assert "standalone" in blob.lower()
        # Must not tell the model to put step formulas in ```math fences.
        assert "NEVER indent a ```math fence inside that list item" not in blob
    # Numbered moves: the reply policy every maths pack closes with states them once.
    assert "numbered" in MATH_REPLY_POLICY.lower() and "steps" in MATH_INTENT_HINT.lower()
    assert "integral" in MATH_INTENT_HINT.lower()
    assert "closed-form asks" in MATH_INTENT_HINT.lower()
    assert "4! = 4" in MATH_INTENT_HINT
    assert "Do NOT emit ```answer" in MATH_INTENT_HINT
    assert "both sides" in MATH_INTENT_HINT.lower()
    assert "Every equality must remain valid" in MATH_INTENT_HINT
    assert "Honor Short mode" in MATH_INTENT_HINT
    assert "full derivation when the user asks" in MATH_INTENT_HINT
    assert "name a standard law or identity once" in MATH_INTENT_HINT
    assert "zero-exponent law" in MATH_INTENT_HINT
    assert "one equals-sign transformation per formula line" in MATH_INTENT_HINT
    assert "empty bullet" in MATH_INTENT_HINT
    assert "SAME line as the `-`" in MATH_INTENT_HINT
    assert "never omit the colon" not in MATH_INTENT_HINT
    assert "You can check" not in MATH_INTENT_HINT
    assert r"\pm" in MATH_INTENT_HINT
    assert "Simplify both branches" in MATH_INTENT_HINT


def test_math_solver_hint_does_not_overclaim_unverified_scope():
    """Stats/combo/NT/matrix used to be listed as broadly "in scope", and
    geometry few-shots embedded concrete dims that taught inventing measures.
    Gate advanced topics on a verified block; mark sample dims illustrative."""
    from app.modules.math.reply_policy import MATH_INTENT_HINT, MATH_SOLVER_HINT

    lower = MATH_SOLVER_HINT.lower()
    assert "never invent" in lower
    assert "illustrative" in lower
    assert "only when a verified" in lower
    assert "do not claim verification" in lower  # safety phrase
    # Physics has an independent prompt. Math must not carry formula,
    # trajectory, or simulation policy for another peer subject.
    assert "trajectory" not in lower
    assert "physics" not in lower
    assert "simulation" not in lower
    from app.modules.math.reply_policy import GRAPH_NO_SUBSTITUTE_CLAUSE

    assert GRAPH_NO_SUBSTITUTE_CLAUSE in MATH_SOLVER_HINT
    # Must not claim bare "are also in scope" without the verified-block gate.
    assert "are also in scope" not in lower
    assert "never invent geometry" in MATH_INTENT_HINT.lower()


@pytest.mark.asyncio
async def test_build_prompt_injects_custom_instructions():
    user = MagicMock()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = "Always answer in bullet points and cite sources."

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        messages = await build_prompt_messages(user, uuid4(), Settings())

    system = system_prompt(messages)
    assert "User's personal instructions:" in system
    assert "Always answer in bullet points and cite sources." in system
    assert "[BEGIN USER PREFERENCES]" in system
    assert "[BEGIN UNTRUSTED CONTENT — user personal instructions]" not in system
    assert "reply-style preferences" in system


@pytest.mark.asyncio
async def test_build_prompt_strips_solver_fences_from_recent_assistant():
    user = MagicMock()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.response_tone = "casual"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = None

    recent = [
        SimpleNamespace(
            id=uuid4(),
            role="assistant",
            content="The solution is below.\n```answer\n42\n```\nKeep this prose.",
        ),
        SimpleNamespace(id=uuid4(), role="user", content="thanks"),
    ]

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch("app.modules.memory.retrieval.get_memory_block", AsyncMock(return_value="")),
        patch("app.modules.todos.build_todos_system_section", AsyncMock(return_value="")),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=recent)),
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False),
            rich_context=False,
        )

    assistant = next(m for m in messages if m["role"] == "assistant")
    assert "```answer" not in assistant["content"]
    assert "Keep this prose." in assistant["content"]
    assert "The solution is below." in assistant["content"]


@pytest.mark.asyncio
async def test_build_prompt_reuses_passed_chat_without_db_fetch():
    user = MagicMock()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.response_tone = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = None

    passed_chat = MagicMock()
    passed_chat.summary = None
    passed_chat.summary_message_count = 0

    get_by_id = AsyncMock()

    with (
        patch.object(chats_repository, "get_by_id", get_by_id),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        await build_prompt_messages(
            user,
            uuid4(),
            Settings(),
            chat=passed_chat,
        )

    get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_prompt_omits_custom_instructions_block_when_empty():
    user = MagicMock()
    user.name = "Test User"
    user.email = "test@example.com"
    user.location = None
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = None

    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=""),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            AsyncMock(return_value=[]),
        ),
    ):
        messages = await build_prompt_messages(user, uuid4(), Settings())

    system = system_prompt(messages)
    assert "User's personal instructions:" not in system


@pytest.mark.asyncio
async def test_build_prompt_includes_memory_and_fits_length_to_the_message():
    user = MagicMock()
    user.name = "Biniyam Mecuriaw"
    user.email = "bmecuriaw@gmail.com"
    user.location = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.response_tone = "funny"

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[AsyncMock(type="preference", text="likes Python")]),
        ),
        patch.object(
            messages_repository,
            "list_recent",
            return_value=[AsyncMock(role="user", content="Hi")],
        ),
        patch(
            "app.modules.memory.selection.format_memory_block",
            return_value="Known facts:\n- [preference] likes Python",
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        messages = await build_prompt_messages(user, uuid4(), Settings())

    assert messages[0]["role"] == "system"
    assert "Biniyam Mecuriaw" in system_prompt(messages)
    # Account email is gated to email/tool intents — omitted on a plain "Hi".
    system = system_prompt(messages)
    assert "bmecuriaw@gmail.com" not in system
    assert "The block below is the user's saved memory" in system  # safety phrase
    # Length follows the message: there is no account-wide setting.
    assert "response length: short" not in system.lower()
    assert "response length: fit the question" in system.lower()
    assert "**HTML UI**" not in system
    assert "Python" in system
    assert CLARIFICATION_HINT in system
    assert messages[-1] == {"role": "user", "content": "Hi"}


@pytest.mark.asyncio
async def test_build_prompt_recalled_count_counts_section_headers():
    """`recalled` must reflect `## {Label}` headers emitted by format_memory_block,
    not "- " bullets (which it never produces). Regression for the chip-always-0 bug."""
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"

    stats = PromptStats()

    # Real format: one `## {Label}` header per injected section.
    block = (
        "Known facts about the user:\n\n## Profile\nLives in Addis\n\n## Preferences\nlikes Python"
    )

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[AsyncMock(type="profile", text="Lives in Addis")]),
        ),
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.selection.format_memory_block",
            return_value=block,
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        await build_prompt_messages(user, uuid4(), Settings(), stats=stats)

    assert stats.recalled == 2
    assert stats.memory_hints == ["Profile", "Preferences"]


@pytest.mark.asyncio
async def test_build_prompt_recalled_count_zero_when_no_memory():
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"

    stats = PromptStats()

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[]),
        ),
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.selection.format_memory_block",
            return_value="",
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        await build_prompt_messages(user, uuid4(), Settings(), stats=stats)

    assert stats.recalled == 0
    assert stats.memory_hints == []


@pytest.mark.asyncio
async def test_build_prompt_includes_response_tone():
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.response_tone = "professional"
    user.memory_enabled = False
    user.locale = "en"
    user.timezone = "UTC"

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[]),
        ),
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.selection.format_memory_block",
            return_value="",
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        messages = await build_prompt_messages(user, uuid4(), Settings())

    system = system_prompt(messages)
    assert "Tone: PROFESSIONAL" in system
    assert "Privacy:" in system
    assert PRIVACY_HINT in system


@pytest.mark.asyncio
async def test_build_prompt_includes_locale_hint_for_amharic():
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.response_tone = "casual"
    user.memory_enabled = False
    user.locale = "am"
    user.timezone = "UTC"

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[]),
        ),
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.selection.format_memory_block",
            return_value="",
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        messages = await build_prompt_messages(user, uuid4(), Settings())

    system = system_prompt(messages)
    assert "Amharic" in system
    assert "locale code: am" in system
    assert locale_system_hint("am") in system


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Who am I", True),
        ("who am i?", True),
        ("What am I", True),
        ("What am I doing", False),
        ("Tell me about me", True),
        ("Where am I?", False),
        ("What's my email?", False),
        ("What's my name?", False),
    ],
)
def test_is_broad_self_question(text, expected):
    assert is_broad_self_question(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("hi", True),
        ("hi\u200b", True),
        ("Thanks!", True),
        ("ok", True),
        ("Hello there", False),
        ("What's on my calendar today?", False),
        ("add eggs to groceries", False),
        ("yes", True),
        ("go", True),
        ("sure", True),
        # A reaction is not a greeting: it keeps the full path ("really?" can challenge a solve).
        ("Oh really?", False),
        ("oh yeah", False),
        ("Why?", False),
        ("x", False),
        ("X", False),
        ("y", False),
    ],
)
def test_is_lightweight_chat_turn(text, expected):
    assert is_lightweight_chat_turn(text) is expected


def test_short_confirmation_after_offer_is_not_lightweight():
    from app.modules.turn_reading.routing import is_short_confirmation, prior_looks_like_offer

    offer = "Want me to check the current result?"
    assert is_short_confirmation("yes")
    assert is_short_confirmation("go")
    assert is_short_confirmation("sure")
    assert not is_short_confirmation("hi")
    assert not is_short_confirmation("thanks")
    assert not is_short_confirmation("no")
    assert not is_short_confirmation("y")
    assert prior_looks_like_offer(offer)
    assert not prior_looks_like_offer("The capital of France is Paris.")
    assert is_lightweight_chat_turn("yes", prior_assistant=offer) is False
    assert is_lightweight_chat_turn("go", prior_assistant=offer) is False
    assert is_lightweight_chat_turn("sure", prior_assistant=offer) is False
    assert is_lightweight_chat_turn("thanks", prior_assistant=offer) is True
    assert is_lightweight_chat_turn("no", prior_assistant=offer) is False
    assert is_lightweight_chat_turn("hi", prior_assistant=offer) is True
    assert is_lightweight_chat_turn("yes") is True
    assert is_lightweight_chat_turn("yes", prior_assistant="The score is 2-1.") is True


@pytest.mark.parametrize("reply", ["No", "nope", "got it", "Understood.", "makes sense", "ok"])
def test_short_answer_to_a_tutor_question_is_not_a_greeting(reply):
    from app.modules.turn_reading.routing import is_short_reply

    question = "This proverb means it's good to do something, even if there's a delay. Understood?"
    assert is_short_reply(reply)
    assert is_lightweight_chat_turn(reply, prior_assistant=question) is False
    # Without a pending question it is still a short ack.
    assert is_lightweight_chat_turn(reply, prior_assistant="Here is the fourth proverb.") is True


@pytest.mark.parametrize("text", ["hi", "Thanks!", "bye", "lol", "What is a proverb?", ""])
def test_social_turns_are_not_short_replies(text):
    from app.modules.turn_reading.routing import is_short_reply

    assert not is_short_reply(text)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("How is ur day", False),
        ("how's your day going", False),
        ("tell me a joke", False),
        ("explain photosynthesis", False),
        ("hi", False),
        ("what do you remember about my diet", True),
        ("what's my name", True),
        ("draft an email to my wife", True),
        ("don't forget my preference for tea", True),
        ("What word did I learn today", False),
        ("what words did I study", False),
        ("how many words have I mastered", False),
        ("what's my vocab progress", False),
        ("what's another word for happy", False),
        ("cuales son mis proyectos", True),
        ("escribeme un correo", True),
        ("የእኔ ፕሮጀክቶች ምንድን ናቸው", True),
        ("explain how transformers work", False),
        ("what was that thing we discussed earlier", True),
        ("what was that thing earlier", True),
    ],
)
def test_needs_rich_context(text, expected):
    assert needs_rich_context(text) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("what should I eat tonight", True),
        ("What should I eat for dinner?", True),
        ("What's for dinner?", True),
        ("I need a quick dinner tonight.", True),
        ("recommend a movie", True),
        ("Recommend a workout.", True),
        ("Plan a workout for me.", True),
        ("Make me a workout plan.", True),
        ("Create my meal plan", True),
        ("Can I eat peanut butter?", True),
        ("Should I drink coffee?", True),
        ("Can you explain how peanut butter is made?", False),
        ("Don't make me a workout plan", False),
        ("Need a workout", True),
        ("what should I wear", True),
        ("gift ideas for a birthday", True),
        ("I'm hungry", True),
        ("qué debería comer", True),
        ("was soll ich essen", True),
        ("hi", False),
        ("thanks", False),
        ("How is ur day", False),
        ("plan my day", False),
        ("what should I focus on today", False),
        ("anything left tonight", False),
        ("what should I return", False),
        ("recommend a library", False),
        ("I need to show you this", False),
        ("Please summarize this movie review for me", False),
        ("I don't need a workout", False),
        ("what should I do", False),
        ("explain photosynthesis", False),
    ],
)
def test_is_personal_advice_question(text, expected):
    assert is_personal_advice_question(text) is expected


@pytest.mark.asyncio
async def test_build_prompt_minimal_for_who_am_i():
    user = MagicMock()
    user.name = "Binalfew Mecuriaw"
    user.email = "secret@example.com"
    user.location = "San Francisco, CA"
    user.location_enabled = True
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"

    chat = MagicMock(project_id=None)
    with (
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(
                return_value=(
                    "Known facts about the user:\n\n"
                    "## Profile\n- Works as a software engineer at Uber.\n\n"
                    "## Preferences\n- Prefers concise, step-by-step explanations."
                )
            ),
        ) as memory_mock,
        patch(
            "app.modules.conversation.history_rag.embed_query_for_prompt",
            AsyncMock(return_value=None),
        ) as history_embed,
    ):
        messages = await build_prompt_messages(
            user,
            AsyncMock(),
            Settings(),
            query_text="What do you know about me?",
            minimal_personal_context=True,
            chat=chat,
        )

    system = system_prompt(messages)
    memory_mock.assert_awaited_once()
    assert history_embed.await_args.kwargs["query"].startswith("Personal details the user stated")
    assert "Binalfew" in system
    assert "software engineer at Uber" in system
    assert "concise, step-by-step" in system
    assert "secret@example.com" not in system
    assert "San Francisco" not in system
    assert BROAD_SELF_ANSWER_HINT in system
    assert "Recall has two features" not in system
    assert "Recall has two todo features" not in system


@pytest.mark.asyncio
async def test_build_prompt_lightweight_hi_skips_memory_and_integrations():
    """A plain greeting must not pay for memory embed / web hints."""
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = "San Francisco, CA"
    user.location_enabled = True
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = "Always mention my cat Fluffy."

    with (
        patch.object(messages_repository, "list_recent", return_value=[]) as recent_mock,
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value="MEMORY SHOULD NOT LOAD"),
        ) as memory_mock,
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value="TODOS SHOULD NOT LOAD"),
        ) as todos_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False, web_search_enabled=True),
            query_text="hi",
            lightweight=True,
            rich_context=False,
        )

    recent_mock.assert_awaited()
    memory_mock.assert_not_awaited()
    todos_mock.assert_not_awaited()
    system = system_prompt(messages)
    assert "Dev" in system
    assert LIGHTWEIGHT_REPLY_HINT in system
    assert "MEMORY SHOULD NOT LOAD" not in system
    assert "TODOS SHOULD NOT LOAD" not in system
    assert "Fluffy" in system
    assert "[BEGIN USER PREFERENCES]" in system
    assert "web_search" not in system.lower()


@pytest.mark.asyncio
async def test_build_prompt_casual_chitchat_loads_memory_without_integrations():
    """A social slim turn keeps custom instructions and skips memory search."""
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = "San Francisco, CA"
    user.location_enabled = True
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = "Always mention my cat Fluffy."
    chat = MagicMock(project_id=None)

    with (
        patch.object(messages_repository, "list_recent", return_value=[]) as recent_mock,
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value="Prefers warm but concise replies."),
        ) as memory_mock,
        patch(
            "app.modules.conversation.history_rag.embed_query_for_prompt",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value="TODOS SHOULD NOT LOAD"),
        ) as todos_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False, web_search_enabled=True),
            query_text="How is ur day",
            lightweight=False,
            rich_context=False,
            chat=chat,
        )

    recent_mock.assert_awaited()
    memory_mock.assert_not_awaited()
    todos_mock.assert_not_awaited()
    system = system_prompt(messages)
    assert "Dev" in system
    assert LIGHTWEIGHT_REPLY_HINT not in system
    assert "Prefers warm but concise replies" not in system
    assert "TODOS SHOULD NOT LOAD" not in system
    assert "Fluffy" in system
    assert "[BEGIN USER PREFERENCES]" in system


@pytest.mark.asyncio
async def test_build_prompt_advice_loads_memory_not_integrations():
    """Dinner recs retrieve memory without Schedule."""
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = "San Francisco, CA"
    user.location_enabled = True
    user.response_tone = "funny"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = None
    chat = MagicMock()

    with (
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value="Prefers vegetarian food. Peanut allergy."),
        ) as memory_mock,
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value="TODOS SHOULD NOT LOAD"),
        ) as todos_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False, web_search_enabled=False),
            query_text="what should I eat tonight",
            lightweight=False,
            rich_context=False,
            advice_memory=True,
            chat=chat,
        )

    memory_mock.assert_awaited()
    assert memory_mock.await_args.kwargs["exclude_sensitive"] is True
    todos_mock.assert_not_awaited()
    system = system_prompt(messages)
    assert "Prefers vegetarian food" in system
    assert "[BEGIN UNTRUSTED CONTENT — saved memory]" in system
    assert ADVICE_PERSONALIZE_HINT in system
    assert "TODOS SHOULD NOT LOAD" not in system


@pytest.mark.asyncio
async def test_build_prompt_teaching_uses_a_known_detail_in_examples():
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = "Addis Ababa"
    user.location_enabled = True
    user.response_tone = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = None
    user.age = None
    user.country = "Ethiopia"
    user.job = None
    user.plan = "free"
    chat = MagicMock()

    with (
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value="User is from Addis Ababa, Ethiopia. User speaks Amharic."),
        ) as memory_mock,
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value="TODOS SHOULD NOT LOAD"),
        ) as todos_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False, web_search_enabled=False),
            query_text="teach me about python variables",
            lightweight=False,
            rich_context=False,
            advice_memory=True,
            chat=chat,
        )

    memory_mock.assert_awaited()
    todos_mock.assert_not_awaited()
    system = system_prompt(messages)
    assert "User speaks Amharic" in system
    assert EXAMPLE_PERSONALIZE_HINT in system
    assert ADVICE_PERSONALIZE_HINT not in system
    assert "TODOS SHOULD NOT LOAD" not in system


@pytest.mark.asyncio
async def test_build_prompt_capabilities_overview_uses_memory_not_email_card():
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = "San Francisco, CA"
    user.location_enabled = True
    user.response_tone = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = None
    chat = MagicMock()

    with (
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value="Building Recall. Learning FastAPI and async Python."),
        ) as memory_mock,
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value="TODOS SHOULD NOT LOAD"),
        ) as todos_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=False, web_search_enabled=False),
            query_text="What can you help me with? Give a few concrete examples.",
            lightweight=False,
            rich_context=False,
            advice_memory=True,
            chat=chat,
        )

    memory_mock.assert_awaited()
    todos_mock.assert_not_awaited()
    system = system_prompt(messages)
    assert "Building Recall" in system
    assert "capabilities overview" in system.lower()
    assert CAPABILITIES_FORMAT_HINT in system
    assert ADVICE_PERSONALIZE_HINT not in system
    assert FORMAT_CONTRACT not in system
    assert "TODOS SHOULD NOT LOAD" not in system
    assert CAPABILITIES_FORMAT_HINT in system


@pytest.mark.asyncio
async def test_build_prompt_forces_rich_context_when_chat_has_attachment_chunks():
    """A casual follow-up after uploading a PDF may not trigger needs_rich_context,
    but if the chat has indexed attachment chunks, RAG retrieval must still run
    so document follow-ups get context. The prompt builder forces rich_context
    when has_chunks_for_chat is True."""
    user = MagicMock()
    user.id = uuid4()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.location_enabled = False
    user.response_tone = "casual"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = None

    rag_block = "ATTACHED DOCUMENT CONTEXT"

    with (
        patch("app.modules.attachments.rag.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.prompt_context.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.conversation.chats_repository.get_by_id",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.conversation.history_rag.embed_query_for_prompt",
            AsyncMock(return_value=None),
        ),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.attachments.chunks_repository.has_chunks_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.attachments.rag.retrieve_for_prompt",
            AsyncMock(return_value=rag_block),
        ) as rag_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=True),
            query_text="what's on page 10?",
            rich_context=False,  # would normally skip RAG, but chunks exist
        )

    system = system_prompt(messages)
    assert rag_block in system
    rag_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_prompt_skips_attachment_rag_probe_when_disabled():
    """Brand-new chats have no indexed chunks — skip the extra Neon probe."""
    user = MagicMock()
    user.id = uuid4()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.location_enabled = False
    user.response_tone = "casual"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = None

    has_chunks = AsyncMock(return_value=True)

    with (
        patch("app.modules.attachments.rag.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.prompt_context.SessionLocal", FakeSessionCM),
        patch(
            "app.modules.conversation.chats_repository.get_by_id",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.conversation.history_rag.embed_query_for_prompt",
            AsyncMock(return_value=None),
        ),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[])),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.attachments.chunks_repository.has_chunks_for_chat",
            has_chunks,
        ),
        patch(
            "app.modules.attachments.rag.retrieve_for_prompt",
            AsyncMock(return_value="SHOULD NOT APPEAR"),
        ) as rag_mock,
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(attachment_rag_enabled=True),
            query_text="help me think through this",
            rich_context=False,
            probe_attachment_rag=False,
        )

    has_chunks.assert_not_awaited()
    rag_mock.assert_not_awaited()
    assert "SHOULD NOT APPEAR" not in system_prompt(messages)


@pytest.mark.asyncio
async def test_build_prompt_uses_preloaded_recent_without_list_recent():
    user = MagicMock()
    user.id = uuid4()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.location_enabled = False
    user.response_tone = "casual"
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.custom_instructions = None

    prior = MagicMock()
    prior.id = uuid4()
    prior.role = "user"
    prior.content = "hi"
    current = MagicMock()
    current.id = uuid4()
    current.role = "user"
    current.content = "6!"

    list_recent = AsyncMock(return_value=[])

    with (
        patch("app.modules.attachments.rag.SessionLocal", FakeSessionCM),
        patch("app.modules.chat.prompt_context.SessionLocal", FakeSessionCM),
        patch.object(messages_repository, "list_recent", list_recent),
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
    ):
        messages = await build_prompt_messages(
            user,
            uuid4(),
            Settings(),
            query_text="6!",
            rich_context=False,
            probe_attachment_rag=False,
            recent_messages=[prior, current],
        )

    list_recent.assert_not_awaited()
    roles = [m["role"] for m in messages if m["role"] != "system"]
    assert roles[-1] == "user"
    assert messages[-1]["content"] == "6!"


def test_classify_turn_mode_hi_is_lightweight():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "hi")

    assert mode.lightweight is True
    assert mode.rich_context is False
    assert mode.advice_memory is False


_CARD_REPLY = (
    "What do you mean by *best*?\n\n```clarify\n"
    '{"request": "Recommend a country.", "questions": [{"id": "region", "label": "Region", '
    '"question": "Which region?", "options": ["Europe", "Asia"]}], "closing": "Compare them.", '
    '"submit": "Find it"}\n```'
)


@pytest.mark.parametrize(
    ("last_reply", "text", "reason"),
    [
        (None, "hi", "social"),
        (None, "thanks!", "social"),
        (None, "explain photosynthesis", "not_light"),
        # A short reply to a question answers it: never small talk.
        ("Want me to set a reminder for that?", "no", "answers_offer"),
        ("Does that make sense?", "yes", "answers_offer"),
        # After a clarify card the message answers the card, whatever it says.
        (_CARD_REPLY, "ok", "answers_card"),
        (_CARD_REPLY, "Europe please", "not_light"),
    ],
)
def test_classify_turn_mode_names_why_a_turn_is_small_talk(
    last_reply: str | None, text: str, reason: str
):
    """The reason is the decision: light exactly when it reads as small talk in its place."""
    from types import SimpleNamespace

    from app.modules.chat.clarify_turn import follows_card
    from app.modules.chat.turn_prep.mode import classify_turn_mode
    from app.modules.turn_reading.routing import is_lightweight_chat_turn, is_short_reply

    recent = [] if last_reply is None else [SimpleNamespace(role="assistant", content=last_reply)]
    mode = classify_turn_mode(recent, text)

    assert mode.lightweight_reason == reason
    prior = last_reply if is_short_reply(text) else None
    assert mode.lightweight is (
        not follows_card(last_reply) and is_lightweight_chat_turn(text, prior_assistant=prior)
    )


@pytest.mark.parametrize(
    ("text", "advice"),
    [
        # A sum that names a meal works from its own numbers, not the user's tastes.
        (
            "I work 9am to 5:30pm every day with a 45 min lunch. "
            "how many hours do I actually work in a 5-day week?",
            False,
        ),
        ("a pizza is cut into 8 slices and I eat 3, what fraction is left?", False),
        ("I eat lunch at 12:30 and dinner at 7pm, how many hours between them?", False),
        ("I drink 3 coffees a day at 95 mg each, how much caffeine is that in a week?", False),
        ("ok so lunch is 45 min and I work 8 hours, how many hours would that be in 5 days", False),
        # Food advice, even with numbers in it, still uses what the user likes.
        ("what should I eat for lunch", True),
        ("how many liters of water should I drink a day", True),
        ("my weight is 80 kg, how much protein should I eat a day?", True),
        ("dinner for 6 at 8pm, how many dishes do I need?", True),
        ("how many hours before bed should I stop eating?", True),
        ("I have 2 hours before dinner, what can I cook?", True),
    ],
)
def test_classify_turn_mode_a_sum_about_a_meal_is_not_food_advice(text: str, advice: bool):
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], text)

    assert mode.advice_memory is advice


def test_classify_turn_mode_draft_follow_up_gets_the_drafts_context():
    """ "Email" after a text-message draft ran slim and signed the email "[Your Name]"."""
    from types import SimpleNamespace

    from app.modules.chat.turn_prep.mode import classify_turn_mode

    history = [
        SimpleNamespace(role="user", content="A text message to my wife"),
        SimpleNamespace(role="assistant", content="```message\nHey love, thinking of you.\n```"),
        SimpleNamespace(role="user", content="Email"),
    ]
    mode = classify_turn_mode(history, "Email")

    assert mode.rich_context is True


def test_classify_turn_mode_skips_history_for_lines_that_change_no_draft():
    from types import SimpleNamespace

    from app.modules.chat.turn_prep.mode import classify_turn_mode

    draft = [
        SimpleNamespace(role="user", content="A text message to my wife"),
        SimpleNamespace(role="assistant", content="```message\nHey love.\n```"),
    ]

    mode = classify_turn_mode(draft, "what is the capital of France")

    assert mode.rich_context is False


def test_classify_turn_mode_no_draft_in_history_stays_slim():
    from types import SimpleNamespace

    from app.modules.chat.turn_prep.mode import classify_turn_mode

    history = [
        SimpleNamespace(role="user", content="what is the capital of France"),
        SimpleNamespace(role="assistant", content="Paris."),
    ]
    mode = classify_turn_mode(history, "make it shorter")

    assert mode.rich_context is False


def test_classify_turn_mode_yes_after_offer_is_not_lightweight():
    from types import SimpleNamespace

    from app.modules.chat.turn_prep.mode import classify_turn_mode

    prior = SimpleNamespace(role="assistant", content="Want me to check the current result?")

    mode = classify_turn_mode([prior], "yes")

    assert mode.lightweight is False


def test_classify_turn_mode_no_after_a_question_is_not_lightweight():
    from types import SimpleNamespace

    from app.modules.chat.turn_prep.mode import classify_turn_mode

    prior = SimpleNamespace(
        role="assistant",
        content="Better late than never: it's good to act even after a delay. Understood?",
    )

    mode = classify_turn_mode([prior], "No")

    assert mode.lightweight is False


def test_classify_turn_mode_hi_ignores_the_last_assistant():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    question = MagicMock(role="assistant", content="Want me to check the current result?")

    mode = classify_turn_mode([question], "hi")

    assert mode.lightweight is True


@pytest.mark.parametrize(
    ("text", "advice"),
    [
        ("what should I cook tonight?", True),
        ("what should I eat for dinner?", True),
        ("any good recipe for a quick lunch?", True),
        # Food words in a problem to solve: no recommendation to personalise.
        ("A recipe needs 3 cups of flour for 12 cookies. How many cups for 30 cookies?", False),
        ("A pancake recipe uses 2 eggs for 8 pancakes. How many eggs for 20 pancakes?", False),
        ("How much energy does it take to heat 500 g of milk from 5 °C to 60 °C?", False),
    ],
)
def test_classify_turn_mode_food_in_a_problem_is_not_advice(text, advice):
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], text)

    assert mode.advice_memory is advice


def test_classify_turn_mode_profile_field_loads_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    education = classify_turn_mode([], "What is my education level")
    language = classify_turn_mode([], "My second langauge")

    assert education.advice_memory is True
    assert education.rich_context is False
    assert language.advice_memory is True
    assert language.rich_context is False


def test_classify_turn_mode_profile_pushback_loads_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    language = MagicMock()
    language.role = "user"
    language.content = "My second langauge"
    pushback = MagicMock()
    pushback.role = "user"
    pushback.content = "U don't know. It?"

    mode = classify_turn_mode([language, pushback], "You tell me")

    assert mode.advice_memory is True


def test_classify_turn_mode_teaching_loads_memory_not_rich_context():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "teach me about python variables")

    assert mode.lightweight is False
    assert mode.rich_context is False
    assert mode.advice_memory is True


def test_classify_turn_mode_career_loads_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "how do I prepare for a job interview")

    assert mode.advice_memory is True
    assert mode.rich_context is False


def test_classify_turn_mode_lookup_does_not_load_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "what is the capital of France")

    assert mode.advice_memory is False
    assert mode.rich_context is False


def test_classify_turn_mode_eat_tonight_is_advice_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "what should I eat tonight")

    assert mode.lightweight is False
    assert mode.rich_context is False
    assert mode.advice_memory is True


def test_classify_turn_mode_capabilities_overview_is_advice_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode(
        [],
        "What can you help me with? Give a few concrete examples.",
    )

    assert mode.lightweight is False
    assert mode.rich_context is False
    assert mode.advice_memory is True


def test_classify_turn_mode_milk_preference_is_advice_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "What milk do I drink.")

    assert mode.lightweight is False
    assert mode.advice_memory is True


@pytest.mark.parametrize(
    "text",
    [
        "I need a quick dinner tonight.",
        "Plan a workout for me.",
    ],
)
def test_classify_turn_mode_ordinary_advice_phrasing_loads_memory(text: str):
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], text)

    assert mode.lightweight is False
    assert mode.rich_context is False
    assert mode.advice_memory is True


def test_classify_turn_mode_day_plan_skips_advice_memory():
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    mode = classify_turn_mode([], "anything left tonight")

    assert mode.day_planning is True
    assert mode.rich_context is True
    assert mode.advice_memory is False


def _augment_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "instant_reply": None,
        "lightweight": False,
        "minimal_personal": False,
        "day_planning": False,
        "ambiguous_nearby": False,
        "rich_context": False,
        "needs_math": False,
        "needs_search": False,
        "needs_chem": False,
    }
    base.update(overrides)
    return base


def test_should_augment_web_and_tools_skips_slim_casual_without_intent():
    """Coaching openers are not greetings but must not pay web/math/chem I/O."""
    from app.modules.chat.turn_prep.mode import _should_augment_web_and_tools

    assert _should_augment_web_and_tools(**_augment_kwargs()) is False
    assert _should_augment_web_and_tools(**_augment_kwargs(rich_context=True)) is True
    assert _should_augment_web_and_tools(**_augment_kwargs(needs_search=True)) is True
    assert _should_augment_web_and_tools(**_augment_kwargs(needs_math=True)) is True
    assert _should_augment_web_and_tools(**_augment_kwargs(needs_chem=True)) is True


@pytest.mark.asyncio
async def test_build_prompt_passes_client_timezone():
    user = MagicMock()
    user.name = "Dev User"
    user.email = "dev@example.com"
    user.location = None
    user.response_tone = "funny"
    user.memory_enabled = False
    user.locale = "en"
    user.timezone = "UTC"

    load_todos = AsyncMock(return_value=None)

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[]),
        ),
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.memory.selection.format_memory_block",
            return_value="",
        ),
        patch(
            "app.modules.todos.build_todos_system_section",
            load_todos,
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.services.time_context.format_time_context",
            return_value="LOCAL_TIME_BLOCK",
        ) as format_time,
    ):
        await build_prompt_messages(
            user,
            uuid4(),
            Settings(),
            client_timezone="America/New_York",
        )

    load_todos.assert_awaited_once()
    assert load_todos.await_args.kwargs["client_timezone"] == "America/New_York"
    format_time.assert_called_once_with("America/New_York", "en", None)


def test_is_short_letter_answer():
    from app.modules.web_search import is_short_letter_answer

    assert is_short_letter_answer("B") is True
    assert is_short_letter_answer("c.") is True
    assert is_short_letter_answer("Is it a?") is True
    assert is_short_letter_answer("hello") is False


def test_format_user_profile_block_includes_fields():
    user = MagicMock()
    user.name = "Ada Lovelace"
    user.email = "ada@example.com"
    user.plan = "pro"
    user.location = "London"
    user.location_enabled = True
    user.age = 36
    user.country = "United Kingdom"
    user.job = "Mathematician"
    block = format_user_profile_block(user, include_email=True)
    assert "Ada Lovelace" in block
    assert "ada@example.com" in block
    assert "Plan: pro" in block
    assert "London" in block
    assert "Age: 36" in block
    assert "Country: United Kingdom" in block
    assert "Job: Mathematician" in block


def test_format_user_profile_block_omits_email_by_default():
    user = MagicMock()
    user.name = "Ada"
    user.email = "ada@example.com"
    user.plan = "free"
    user.location = None
    user.location_enabled = False
    user.age = None
    user.country = None
    user.job = None
    block = format_user_profile_block(user)
    assert "ada@example.com" not in block
    assert "Email:" not in block


@pytest.mark.parametrize(
    "text, expected",
    [
        (None, False),
        ("", False),
        ("Hi there", False),
        ("What's my email?", True),
        ("draft an email to my boss", True),
        ("check my inbox", False),
    ],
)
def test_should_include_profile_email(text, expected):
    assert should_include_profile_email(text) is expected


def test_format_user_profile_block_omits_empty_structured_fields():
    user = MagicMock()
    user.name = "Ada"
    user.email = "ada@example.com"
    user.plan = "free"
    user.location = None
    user.location_enabled = False
    user.age = None
    user.country = "  "
    user.job = None
    block = format_user_profile_block(user)
    assert "Plan: free" in block
    assert "Age:" not in block
    assert "Country:" not in block
    assert "Job:" not in block


def test_format_user_name_only_block_uses_first_name():
    user = MagicMock()
    user.name = "Ada Lovelace"
    block = format_user_name_only_block(user)
    assert "Ada" in block
    # A slim turn signs drafts too: "[Your Name]" came from a who-am-I-only name.
    assert "Sign emails and messages the user will send as Ada." in block
    assert "Lovelace" not in block


def test_format_user_name_only_block_missing_name():
    user = MagicMock()
    user.name = "   "
    block = format_user_name_only_block(user)
    assert "not on file" in block
    assert "Never write [Your Name]" in block


def test_format_user_profile_block_signs_drafts_with_the_first_name():
    user = MagicMock()
    user.name = "Ada Lovelace"
    user.email = None
    user.plan = "free"
    user.age = None
    user.country = None
    user.job = None
    user.location = None
    user.location_enabled = False
    block = format_user_profile_block(user)
    assert "Sign emails and messages the user will send as Ada." in block


def _clock_user() -> MagicMock:
    return make_user(
        name="Dev User",
        email="dev@example.com",
        location=None,
        location_enabled=False,
        response_tone=None,
        memory_enabled=False,
        locale="en",
        timezone="America/Indiana/Indianapolis",
        custom_instructions=None,
    )


async def _system_for(text: str, *, lightweight: bool) -> str:
    with patch.object(messages_repository, "list_recent", return_value=[]):
        messages = await build_prompt_messages(
            _clock_user(),
            uuid4(),
            Settings(attachment_rag_enabled=False, web_search_enabled=False),
            query_text=text,
            lightweight=lightweight,
            rich_context=False,
        )
    return system_prompt(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "lightweight"),
    [("Oh really?", False), ("wow", False), ("Is that so?", False), ("Okay", True), ("hi", True)],
)
async def test_a_casual_turn_gets_no_clock_to_read_back(text: str, lightweight: bool) -> None:
    """Live 2026-10-26: "Oh really?" was answered "Yes, today is Monday, October 26, 2026, and
    it's 2:14 PM EDT." The clock is the freshest line of the prompt and there was nothing
    else to answer."""
    assert "Current local time" not in await _system_for(text, lightweight=lightweight)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "lightweight"),
    [
        ("thanks, see you tomorrow", True),
        ("ok what day is it", True),
        ("How old is Obama?", False),
        ("Why is the sky blue?", False),
        ("Really? Explain more", False),
        ("Why?", False),
    ],
)
async def test_a_turn_that_may_need_the_clock_keeps_it(text: str, lightweight: bool) -> None:
    assert "Current local time" in await _system_for(text, lightweight=lightweight)


@pytest.mark.parametrize(
    ("text", "reaction"),
    [
        ("Oh really?", True),
        ("Really?", True),
        ("wow", True),
        ("hmm", True),
        ("Seriously?", True),
        ("Is that so?", True),
        ("Really? Explain more", False),
        ("Why?", False),
        ("Interesting question about taxes", False),
        ("hi", False),
        ("", False),
        (None, False),
    ],
)
def test_is_reaction_turn(text: str | None, reaction: bool) -> None:
    from app.modules.turn_reading.reactions import is_reaction_turn

    assert is_reaction_turn(text) is reaction


@pytest.mark.parametrize("text", ["Oh really?", "oh yeah", "Really?", "oh okay"])
def test_a_reaction_keeps_its_routing_after_an_offer_or_a_solve(text: str) -> None:
    """Making reactions lightweight would have dropped the offer guard and a solve's follow-up."""
    from app.modules.chat.turn_prep.mode import classify_turn_mode

    recent = [
        SimpleNamespace(role="user", content="17*23"),
        SimpleNamespace(role="assistant", content="391. Want me to draft the email?"),
    ]
    assert classify_turn_mode(recent, text).lightweight is False
