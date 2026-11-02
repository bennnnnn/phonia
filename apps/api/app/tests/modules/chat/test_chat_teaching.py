"""Teach-me turns run as a lesson, and the next turn continues it."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.prompt_builder import build_prompt_messages
from app.modules.chat.prompt_constants import (
    COMPACT_RESPONSE_FORMAT_HINT,
    HOWTO_FORMAT_HINT,
    LEARNING_PLAN_HINT,
    PERSONAL_DISCLOSURE_HINT,
    SHORT_RESPONSE_FORMAT_HINT,
    STEPS_FORMAT_HINT,
    TEACHING_HINT,
    WALKTHROUGH_HINT,
    learning_plan_daily_contract,
    programming_lesson_contract,
)
from app.modules.chat.prompt_constants.lesson_flow import OUTLINE_PICK_HINT, lesson_continue_hint
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.conversation import chats_repository, messages_repository
from app.modules.turn_reading.lesson_flow import (
    active_lesson_step,
    lesson_step,
    outline_awaits_pick,
)
from app.modules.turn_reading.routing import is_lightweight_chat_turn
from app.modules.turn_reading.teaching import is_learning_plan_request, is_teaching_request
from app.tests.modules.chat.chat_test_support import system_prompt

LESSON_ONE = (
    "Let's learn Python dictionaries 🐍 — the structure behind every JSON body your API returns.\n\n"
    "### Lesson 1: Dictionaries\n\n"
    "### 1. Understand the idea\n\n"
    "A dictionary stores key-value pairs.\n\n"
    "```python\ncar = {'brand': 'Toyota', 'year': 2024}\nprint(car['brand'])\n```\n\n"
    "### 2. Your turn\n\n"
    "```quiz\n"
    '{"question": "What will this print?", "options": ["Toyota", "brand", "2024", "0"], '
    '"answer": 0, "explanation": "car[\'brand\'] reads the value under the key brand."}\n'
    "```\n\n"
    "Once you get this, we'll move to adding, updating and looping over keys."
)


@pytest.mark.parametrize(
    "text",
    [
        "Teach me python dictionary step by step",
        "can you teach me how photosynthesis works",
        "Help me learn SQL joins",
        "I want to learn recursion",
        "I'd like to learn Spanish verbs",
        "I would like to learn how derivatives work",
        "i wanna learn react hooks",
        "tutor me in chemistry",
        "become my tutor for Python",
        "act as my teacher for algebra",
        "teach me how to pass an L3 coding interview",
        "Give me a lesson on fractions",
        "a crash course in git",
        "Enséñame los diccionarios de Python",
        "apprends-moi les boucles en Python",
        "Bring mir Python bei",
        "Ich möchte Python lernen",
        "insegnami le frazioni",
        "me ensina a usar listas",
        "научи меня python",
        "bana python sözlükleri öğret",
        "ፓይተን አስተምረኝ",
        # Learning a skill, not doing a task.
        "teach me how to code in python",
        "teach me how to use python dictionaries",
        "help me learn how to play chess",
        "teach me how recursion works",
        # A later "how to" is part of the topic, not the ask.
        "Teach me python dictionaries and how to loop over them",
    ],
)
def test_teaching_request_detected(text):
    assert is_teaching_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "How to install python step by step",
        "Teach me how to install Docker",
        "teach me to set up a React project",
        "What is a python dictionary?",
        "Explain photosynthesis step by step",
        "Give me a 4-week roadmap to learn Python",
        "Help me understand this error",
        "Who was my teacher last year?",
        # Procedures keep the how-to steps, whatever the verb.
        "Teach me how to bake bread step by step",
        "teach me how to change a tire",
        "teach me how to tie a knot",
        "Can you teach me to cook?",
        "I want to learn how to cook",
        "Walk me through Python dictionaries",
        "Walk me through changing a tire",
        "Walk me through baking bread",
        "Walk me through filing my taxes",
        "",
    ],
)
def test_teaching_request_declines(text):
    assert not is_teaching_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "70 days mastering python from beginner to senior level plan",
        "Give me a 70-day Python mastery plan",
        "Teach me Python in 70 days",
        "Teach me Python over the next 70 days",
        "Create a 70-day Python plan",
        "70-day roadmap for Python",
        "Give me a daily Python curriculum for 70 days",
        "Create a 12-week roadmap to learn backend engineering",
        "learning plan for SQL",
        "roadmap to master FastAPI",
        "Dame un plan de 4 semanas para aprender español",
        "Give me a 30 day plan to learn Spanish",
        "6 week study plan for the SAT",
        "I want to learn guitar in 3 months, make me a plan",
        # Named by subject or goal, not by "learn".
        "30 day plan for calculus",
        "8 week MCAT prep plan",
        "12 week plan to become a data analyst",
        "6 week Spanish plan",
        "Give me a 90 day plan to get good at chess",
        "training plan for my new hires",
    ],
)
def test_learning_plan_request_detected(text):
    assert is_learning_plan_request(text)


def test_only_a_programming_roadmap_ends_on_production_experience() -> None:
    assert "Production-experience note" in learning_plan_daily_contract("30 day Python plan")
    spanish = learning_plan_daily_contract("6 day Spanish plan")
    assert "Checkpoints and milestones" in spanish
    assert "Production" not in spanish


@pytest.mark.parametrize(
    "text",
    [
        "Teach me python dictionary step by step",
        "What is a dictionary?",
        "How to install Docker",
        "Explain recursion",
        "Give me a 30-day workout plan",
        "Create a 12-week business plan",
        "Make a 30-day launch plan for my app",
        "I started learning Python 3 days ago",
        "I've been studying Python for 8 weeks",
        "I studied Python for 70 days and now plan to apply for jobs",
        "Plan my day",
        # Plans for doing, not learning (2026-10-29: the Rome trip came back as a study
        # roadmap with a "Production-experience note").
        "Plan a 3 day trip to Rome for me",
        "Make me a 2 week itinerary for Japan",
        "plan my 2 week Japan trip",
        "plan a 2 week road trip",
        "a 3 day honeymoon plan in Bali",
        "Create a 16 week marathon training plan",
        "Give me a 7 day detox plan",
        "12 week weight loss plan",
        "6 month wedding plan",
        "4 week plan to move apartments",
    ],
)
def test_learning_plan_request_declines_non_plans(text):
    assert not is_learning_plan_request(text)


@pytest.mark.parametrize(
    "reply, expected",
    [
        (LESSON_ONE, 1),
        ("### Lesson 2: Loops\n\nWhat does it print?", 2),
        ("**Lesson 3: Functions**\n\nWhich one returns first?", 3),
        ("### Lección 2: Valores\n\n¿Qué imprime?", 2),
        ("### Leçon 2 — Accès\n\nQue affiche-t-il ?", 2),
        ("### Урок 4: Итог\n\nЧто выведет код?", 4),
        ("### Lesson 1: A\n\ntext\n\n### Lesson 2: B\n\nWhich one?", 2),
        ('### Lesson 5: Sets\n\n```quiz\n{"question": "Pick one", "options": ["a", "b"]}\n```', 5),
        # Plans, parts and how-tos are not lessons.
        ("### Day 1: Arrive\n\nReady for day 2?", None),
        ("### Step 2/6 — Accessing values\n\nWhat does it print?", None),
        # A lesson that ends without practice is a reference, not a step to continue.
        ("### Lesson 5: Recap\n\nYou're done.", None),
        ("We covered this in Lesson 2: loops?", None),
        ("### Lesson 0: Nothing?", None),
        ("The capital of France is Paris.", None),
        (None, None),
    ],
)
def test_lesson_step(reply, expected):
    assert lesson_step(reply) == expected


def test_active_lesson_step_reads_only_the_latest_assistant_reply():
    messages = [
        SimpleNamespace(role="user", content="Teach me dictionaries"),
        SimpleNamespace(role="assistant", content=LESSON_ONE),
        SimpleNamespace(role="user", content="red"),
    ]
    assert active_lesson_step(messages) == 1
    messages.append(SimpleNamespace(role="assistant", content="That lesson is now stopped."))
    assert active_lesson_step(messages) is None


def test_lesson_continue_hint_grades_the_practice_then_teaches_the_next_lesson():
    hint = lesson_continue_hint(2)
    assert "ALREADY SEEN Lesson 2" in hint and "Do not repeat Lesson 2" in hint
    assert '"Correct! 🎉"' in hint and '"Not quite"' in hint
    assert "Then teach Lesson 3" in hint
    assert "do not ask them to try again" in hint


def test_lesson_continue_hint_handles_confusion_accidents_and_mode_switches():
    hint = lesson_continue_hint(2)
    assert "different way" in hint and "`### Lesson 2: ...` title" in hint
    assert "do not grade it" in hint
    assert "everything at once" in hint and "cheat sheet" in hint
    assert "without a greeting or an outline" in hint


def test_lesson_continue_hint_keeps_the_lesson_shape():
    hint = lesson_continue_hint(1)
    assert "```quiz" in hint and "```array" in hint and "```steps" in hint
    assert "`### Lesson N: <topic>`" in hint


def _hints(text, *, lesson=None, compact=False, outline_pick=False):
    return _style_format_hints(
        query_text=text,
        is_day_plan=False,
        minimal_personal_context=False,
        compact=compact,
        lesson=lesson,
        outline_pick=outline_pick,
    )


def test_teach_request_gets_a_lesson_not_a_howto():
    hints = _hints("Teach me python dictionary step by step")
    assert TEACHING_HINT in hints
    assert LEARNING_PLAN_HINT not in hints
    assert HOWTO_FORMAT_HINT not in hints


def test_explicit_teach_request_beats_comparison_layout():
    from app.modules.chat.prompt_constants import COMPARISON_FORMAT_HINT

    hints = _hints("Teach me the difference between Python vs Java")
    assert TEACHING_HINT in hints
    assert COMPARISON_FORMAT_HINT not in hints


def test_70_day_learning_plan_gets_complete_roadmap_policy():
    hints = _hints("70 days mastering python from beginner to senior level plan")
    assert LEARNING_PLAN_HINT in hints
    assert TEACHING_HINT not in hints
    joined = "\n".join(hints)
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined
    assert LEARNING_PLAN_HINT in joined


def test_programming_lesson_requires_a_tagged_code_example():
    joined = "\n".join(_hints("Teach me Python dictionaries step by step"))
    assert "language-tagged blocks" in joined
    assert "line by line" in joined
    assert "HARD PROGRAMMING-LESSON ACCEPTANCE CHECK" in joined
    assert "```python" in joined


@pytest.mark.parametrize("hint", [TEACHING_HINT, WALKTHROUGH_HINT])
def test_lesson_hints_follow_the_chatgpt_lesson_shape(hint):
    assert "### Lesson N: <topic>" in hint
    assert "`### 1. Understand the problem`" in hint
    assert "Your turn" in hint and "```quiz" in hint
    assert "```array" in hint and "```steps" in hint
    assert "$O(n^2)$" in hint
    assert "Once you get this, we'll move to" in hint
    assert "No course outline" in hint
    assert "Since you already know some Python basics" in hint
    assert "never group lines" in hint and "Never write `>>>` prompts" in hint
    assert "`Test it:`" in hint and "`Output:`" in hint and "`**How it works:**`" in hint
    assert '"caption": "2 + 7 = 9"' in hint and '"title": "Think of a Python list' in hint
    assert '"label": "Exercise 1"' in hint and '"code":' in hint


def test_named_daily_plan_gets_every_required_label_in_order():
    contract = learning_plan_daily_contract("Create a 70-day Python plan")
    assert "exactly 70 separate Markdown lines" in contract
    assert "Day 1 | Day 2 | Day 3" in contract
    assert "Day 68 | Day 69 | Day 70" in contract
    assert contract.index("Day 1") < contract.index("Day 70")
    assert "### Checkpoints and milestones" in contract
    assert "Production experience takes longer than this roadmap." in contract
    assert "exactly five short runnable ```python code blocks" in contract
    assert "Day 14, Day 28, Day 42, Day 56, Day 70" in contract
    joined = "\n".join(_hints("Create a 70-day Python plan"))
    assert contract in joined


def test_non_daily_plan_does_not_get_a_daily_label_contract():
    assert learning_plan_daily_contract("Create a Python learning roadmap") == ""
    assert learning_plan_daily_contract("Create a 6-month Python plan") == ""


def test_programming_lesson_contract_uses_named_language_tag():
    contract = programming_lesson_contract("Teach me TypeScript interfaces")
    assert "```typescript" in contract
    assert "inline snippet" in contract
    assert "even when the lesson starts with a concept" in contract
    assert "```quiz" in contract


def test_teach_me_in_70_days_is_a_plan_not_an_interactive_lesson():
    hints = _hints("Teach me Python in 70 days")
    assert LEARNING_PLAN_HINT in hints
    assert TEACHING_HINT not in hints


def test_an_explicit_learning_plan_is_not_crushed_to_short_prose():
    hints = _hints("Give me a 30-day plan to learn FastAPI")
    assert LEARNING_PLAN_HINT in hints
    assert SHORT_RESPONSE_FORMAT_HINT not in hints


# A task asked for step by step is one list of steps, not a plan of weeks or phases.
@pytest.mark.parametrize(
    "query",
    [
        "How to install python step by step",
        "how do I set up my new printer",
        "how to make jollof rice step by step",
        "receta de pan paso a paso",
    ],
)
def test_procedure_gets_numbered_steps_not_a_plan(query: str):
    hints = _hints(query)
    assert STEPS_FORMAT_HINT in hints
    assert HOWTO_FORMAT_HINT not in hints
    assert TEACHING_HINT not in hints


def test_walk_me_through_procedure_is_steps_not_an_interactive_lesson():
    hints = _hints("Walk me through changing a tire")
    assert STEPS_FORMAT_HINT in hints
    assert HOWTO_FORMAT_HINT not in hints
    assert TEACHING_HINT not in hints


# A solver owns a worked problem's layout: no week or phase headings beside it.
def test_a_step_by_step_problem_gets_no_plan_layout():
    hints = _hints("explain step by step how to integrate x^2 sin(x)")
    assert HOWTO_FORMAT_HINT not in hints
    assert STEPS_FORMAT_HINT not in hints


def test_brevity_request_is_not_a_lesson():
    hints = _hints("Briefly teach me python dictionaries in one sentence")
    assert TEACHING_HINT not in hints


def test_answer_to_a_lesson_continues_the_lesson():
    hints = _hints("A", lesson=1)
    assert lesson_continue_hint(1) in hints
    assert TEACHING_HINT not in hints


@pytest.mark.parametrize("answer", ["I'm confused", "I have no idea"])
def test_confusion_mid_lesson_is_an_answer_not_a_disclosure(answer):
    hints = _hints(answer, lesson=2)
    assert lesson_continue_hint(2) in hints
    assert PERSONAL_DISCLOSURE_HINT not in hints


def test_new_teach_request_starts_a_new_lesson():
    hints = _hints("Teach me python sets", lesson=3)
    assert TEACHING_HINT in hints
    assert not any("A lesson is in progress" in hint for hint in hints)


def test_full_roadmap_request_exits_an_active_lesson():
    hints = _hints("Give me a 30-day roadmap to learn Python", lesson=3)
    assert LEARNING_PLAN_HINT in hints
    assert not any("A lesson is in progress" in hint for hint in hints)


def test_random_input_mid_lesson_keeps_adaptive_continuation_policy():
    hints = _hints("Bad bdbd head hdjjd jdjdd", lesson=1)
    joined = "\n".join(hints)
    assert "Accidental or unclear input: do not grade it" in joined
    assert "teach Lesson 2" in joined
    assert "Do not repeat Lesson 1" in joined


def test_next_lesson_drops_the_no_headings_rule():
    hints = _hints("B", lesson=2)
    assert lesson_continue_hint(2) in hints
    assert SHORT_RESPONSE_FORMAT_HINT not in hints


def test_short_reply_to_a_lesson_is_not_lightweight():
    # The practice is a quiz card and the reply ends on the preview, not a "?".
    assert is_lightweight_chat_turn("ok", prior_assistant=LESSON_ONE) is False
    assert is_lightweight_chat_turn("thanks", prior_assistant=LESSON_ONE) is True


def _user():
    user = MagicMock()
    user.name = "Bini"
    user.email = "bini@example.com"
    user.location = None
    user.response_tone = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = None
    return user


async def _system_prompt(recent, query):
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch("app.modules.memory.retrieval.get_memory_block", AsyncMock(return_value="")),
        patch("app.modules.todos.build_todos_system_section", AsyncMock(return_value="")),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=recent)),
    ):
        messages = await build_prompt_messages(
            _user(),
            uuid4(),
            Settings(attachment_rag_enabled=False),
            query_text=query,
            rich_context=False,
            current_user_message_id=recent[-1].id,
        )
    return system_prompt(messages)


@pytest.mark.asyncio
async def test_ok_after_a_lesson_asks_for_the_next_lesson():
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content="Teach me python dictionary step by step"),
        SimpleNamespace(id=uuid4(), role="assistant", content=LESSON_ONE),
        SimpleNamespace(id=uuid4(), role="user", content="ok"),
    ]
    system = await _system_prompt(recent, "ok")
    assert "A lesson is in progress" in system
    assert "teach Lesson 2" in system
    # "ok" would otherwise get the casual one-liner layout.
    assert COMPACT_RESPONSE_FORMAT_HINT not in system


@pytest.mark.asyncio
async def test_random_input_after_a_lesson_does_not_restart_or_regrade_it():
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content="Teach me python dictionary step by step"),
        SimpleNamespace(id=uuid4(), role="assistant", content=LESSON_ONE),
        SimpleNamespace(id=uuid4(), role="user", content="Bad bdbd head hdjjd jdjdd"),
    ]
    system = await _system_prompt(recent, "Bad bdbd head hdjjd jdjdd")
    assert "A lesson is in progress" in system
    assert "Do not repeat Lesson 1" in system
    assert "Accidental or unclear input: do not grade it" in system
    assert "teach Lesson 2" in system


@pytest.mark.asyncio
async def test_ordinary_follow_up_gets_no_lesson_hint():
    recent = [
        SimpleNamespace(id=uuid4(), role="user", content="What is the capital of France?"),
        SimpleNamespace(id=uuid4(), role="assistant", content="Paris."),
        SimpleNamespace(id=uuid4(), role="user", content="And of Spain?"),
    ]
    system = await _system_prompt(recent, "And of Spain?")
    assert "A lesson is in progress" not in system


@pytest.mark.parametrize(
    "text",
    [
        "I want to know american history",
        "I'd like to know more about black holes",
        "I need to understand calculus",
    ],
)
def test_wanting_to_know_a_subject_is_a_lesson(text: str) -> None:
    assert TEACHING_HINT in _hints(text)


@pytest.mark.parametrize(
    "text",
    [
        "I want to know if it will rain tomorrow",
        "I want to know my balance",
        "I want to know the price of gold",
        "I want to know about the new tesla model",
        "I want to know your opinion",
    ],
)
def test_wanting_to_know_a_fact_is_not_a_lesson(text: str) -> None:
    assert TEACHING_HINT not in _hints(text)


@pytest.mark.parametrize(
    "text",
    [
        "help me understand two sum in python",
        "walk me through quicksort",
        "I don't understand recursion",
        "explain merge sort step by step",
    ],
)
def test_understanding_one_idea_is_a_walkthrough_not_a_lesson(text: str) -> None:
    hints = _hints(text)
    assert WALKTHROUGH_HINT in hints
    assert TEACHING_HINT not in hints


@pytest.mark.parametrize("text", ["I don't get it", "help me understand this"])
def test_confusion_without_a_subject_is_not_a_walkthrough(text: str) -> None:
    assert WALKTHROUGH_HINT not in _hints(text)


@pytest.mark.parametrize("hint", [TEACHING_HINT, WALKTHROUGH_HINT])
def test_practice_heading_fits_the_subject_and_the_quiz_fence_stands_alone(hint):
    # "Teach me american history" ended on "Your turn — predict the output" and a
    # ```quiz line with its JSON glued on.
    assert "`### N. Your turn — predict the output`" not in hint
    assert "history: `— check your understanding`" in hint
    assert "```quiz alone on its line and the JSON on the next" in hint


OUTLINE = (
    "Python lets you automate chores and analyse data.\n\n"
    "1. **Variables and types** — store values\n2. **Lists and loops** — work through many\n"
    "3. **Dictionaries** — look things up by name\n\n"
    "New to it, or do you know some already? Pick a number."
)


def test_teaching_hint_outlines_a_whole_subject_and_teaches_one_idea():
    assert "A whole subject" in TEACHING_HINT and "do not teach yet" in TEACHING_HINT
    assert "One idea" in TEACHING_HINT and "nothing past it" in TEACHING_HINT
    assert "an outline of a whole language has no code" in programming_lesson_contract(
        "teach me python"
    )


def _turns(*pairs):
    return [SimpleNamespace(role=role, content=content) for role, content in pairs]


def test_outline_awaits_pick_after_a_teach_me_answered_with_an_outline():
    assert outline_awaits_pick(_turns(("user", "teach me python"), ("assistant", OUTLINE)))


@pytest.mark.parametrize(
    "turns",
    [
        # A lesson, not an outline: the lesson goes on instead.
        (("user", "teach me python dictionaries"), ("assistant", LESSON_ONE)),
        # Not a teach-me.
        (("user", "what can python do?"), ("assistant", OUTLINE)),
        # The outline asked nothing.
        (("user", "teach me python"), ("assistant", OUTLINE.replace("?", "."))),
        # An outline further back: the conversation moved on.
        (
            ("user", "teach me python"),
            ("assistant", OUTLINE),
            ("user", "actually, what's the capital of Peru?"),
            ("assistant", "Lima."),
        ),
        (),
    ],
)
def test_outline_awaits_pick_declines(turns):
    assert not outline_awaits_pick(_turns(*turns))


@pytest.mark.parametrize("answer", ["3", "start", "I'm a beginner", "I want to analyse data"])
def test_reply_to_an_outline_teaches_lesson_one(answer):
    hints = _hints(answer, outline_pick=True)
    assert OUTLINE_PICK_HINT in hints
    assert PERSONAL_DISCLOSURE_HINT not in hints
    assert "`### Lesson N: <topic>`" in OUTLINE_PICK_HINT


def test_new_teach_request_after_an_outline_starts_over():
    hints = _hints("teach me cooking", outline_pick=True)
    assert TEACHING_HINT in hints and OUTLINE_PICK_HINT not in hints
