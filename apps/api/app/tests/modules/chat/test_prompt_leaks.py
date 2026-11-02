"""A sentence that tells the user about the prompt's own parts comes off a reply."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.chat.finalize_contracts import STOPPED_REPLY_PASSES
from app.modules.chat.finalize_passes import FINALIZE_PASSES
from app.modules.chat.prompt_leaks import drop_prompt_leaks, drop_prompt_leaks_pass

ANSWER = "For a first investment, a low-cost index fund is a sound start."
# The live reply (2026-10-25), on an investing question.
LIVE_LEAK = (
    "The memory block contains details that don't match this conversation. It names a "
    "different person and preferences that conflict with what you've told me, so I'm "
    "setting it aside and answering from what you've shared, Dev."
)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (f"{LIVE_LEAK}\n\n{ANSWER}", ANSWER),
        (f"{LIVE_LEAK} {ANSWER}", ANSWER),
        (
            f"Sure thing, Dev! Your saved memory block lists a nursing exam. {ANSWER}",
            f"Sure thing, Dev! {ANSWER}",
        ),
        (f"My system prompt says your name on file is Dev. {ANSWER}", ANSWER),
        (f"Per the [Chemistry note], no IUPAC name came back. {ANSWER}", ANSWER),
        (f"[BEGIN UNTRUSTED CONTENT — saved memory] was empty.\n\n{ANSWER}", ANSWER),
        (
            f"Hi Dev!\n\n- The profile block in this chat says Chicago.\n- {ANSWER}",
            f"Hi Dev!\n\n- {ANSWER}",
        ),
        # The sentence that points back at the leak goes with it; the next one stays.
        (
            f"The memory block names a different person. That is set aside. {ANSWER}",
            f"That is set aside. {ANSWER}",
        ),
        (
            f"The memory block names a different person. It conflicts with what you've told "
            f"me. {ANSWER}",
            ANSWER,
        ),
    ],
)
def test_a_sentence_about_the_prompt_comes_off(reply: str, expected: str) -> None:
    assert drop_prompt_leaks(reply, "how should I start investing?") == expected


@pytest.mark.parametrize(
    "reply",
    [
        # Everyday meanings of the same words.
        "When you call `free()`, the memory block goes back to the heap.",
        "malloc returns a pointer to a memory block of at least the requested size.",
        "A system prompt sets the model's role before the first user message.",
        "Your profile block in the CMS template holds the avatar and bio.",
        # Words about the user without a prompt part.
        "Earlier I called you Sam; sorry, Dev. Here is the plan for this conversation.",
        f"From what you've told me, a low-risk start fits. {ANSWER}",
        # Inside code, a table or a heading nothing changes.
        "```python\n# the memory block on file for this conversation\nx = 1\n```",
        "Use `system prompt on file` as the key.",
        "| term | meaning |\n| --- | --- |\n| memory block about you | a note |",
        "## The memory block in this conversation",
        ANSWER,
        # Second-person words an answer about a CMS or an LLM uses (review, 2026-10-25).
        "Keep your name and tone rules in the system message so the model knows about you.",
        "Add a profile block to the sidebar so it shows your name and avatar.",
        "The profile block displays information about you to visitors.",
        # "On file" that is not this user's record.
        "When you free it, the allocator marks this memory block as free; on file systems "
        "it differs.",
        "Each memory block on file is tracked by the bitmap. It is efficient.",
        # A quote is the quoted text.
        '> "The system prompt is set aside in this chat," she said.\n\nFrom the novel.',
        "> The system prompt in this conversation is fixed.",
        # Sentences that only point back after a leak go; here there is none.
        "Your memory block is misaligned. This is what you've told me about the board.",
    ],
)
def test_other_replies_are_left_alone(reply: str) -> None:
    assert drop_prompt_leaks(reply, "why does free crash?") == reply


def test_a_chat_about_language_models_keeps_its_reply() -> None:
    reply = "The system message in this conversation sets the tone. It works best short."
    asks = ["how do I write instructions for an LLM agent?", "and for ChatGPT?"]
    for asked in asks:
        assert drop_prompt_leaks(reply, asked) == reply
    # An earlier message in the chat says what it is about.
    assert drop_prompt_leaks(reply, "and the tone?", "how do system prompts work?") == reply


@pytest.mark.parametrize(
    "earlier",
    [
        "I asked ChatGPT earlier but it was wrong",
        "I'm a GPT user",
        "give me a writing prompt for my class",
        "my boss wants a prompt reply",
    ],
)
def test_a_passing_mention_of_chatgpt_or_a_prompt_keeps_the_guard(earlier: str) -> None:
    reply = f"{LIVE_LEAK}\n\n{ANSWER}"
    assert drop_prompt_leaks(reply, "how should I invest 10k?", earlier) == ANSWER


@pytest.mark.parametrize(
    "query",
    [
        "What does your system prompt say about me?",
        "write a system prompt for my support bot",
        "what's in the memory block?",
    ],
)
def test_a_turn_that_asks_about_prompts_keeps_its_reply(query: str) -> None:
    reply = f"My system prompt says your name on file is Dev. {ANSWER}"
    assert drop_prompt_leaks(reply, query) == reply


def test_a_reply_that_is_only_a_leak_is_kept() -> None:
    assert drop_prompt_leaks(LIVE_LEAK, "hi") == LIVE_LEAK


def _state(
    text: str, *, server_text: bool = False, earlier: tuple[str, ...] = ()
) -> SimpleNamespace:
    ctx = SimpleNamespace(
        user_message_content="how do I start investing?",
        prompt_messages=[{"role": "system", "content": "about prompts"}]
        + [{"role": "user", "content": line} for line in earlier],
    )
    return SimpleNamespace(text=text, ctx=ctx, server_text=server_text)


def test_the_pass_cleans_a_model_reply_and_never_server_text() -> None:
    reply = f"{LIVE_LEAK}\n\n{ANSWER}"
    assert drop_prompt_leaks_pass(_state(reply)) == ANSWER  # type: ignore[arg-type]
    assert drop_prompt_leaks_pass(_state(reply, server_text=True)) == reply  # type: ignore[arg-type]


def test_the_pass_reads_the_users_recent_messages() -> None:
    reply = f"{LIVE_LEAK}\n\n{ANSWER}"
    on_prompts = _state(reply, earlier=("write me a system prompt",))
    assert drop_prompt_leaks_pass(on_prompts) == reply  # type: ignore[arg-type]


def test_the_pass_runs_on_every_reply_and_a_stopped_one() -> None:
    names = [finalize_pass.name for finalize_pass in FINALIZE_PASSES]
    assert names.index("prompt_leaks") == names.index("meta_notes") + 1
    assert "prompt_leaks" in STOPPED_REPLY_PASSES


# An instruction copied from the prompt opened a Class 8 speed answer (2026-10-30).
_PHYSICS_RULES = (
    "Physics answers:\n  - This is a physics problem. Do not describe the work as math, "
    "algebra, or solving equations.\n  - When verified results appear in a [BEGIN VERIFIED "
    "PHYSICS] block, use those exact numbers and units. Do not recompute. If no verified "
    "block is present, do not claim verification.\n"
    "Saved facts: Bini is building a recipe app called Spoon. Use metric units always."
)
_ECHO = (
    "This is a physics question. Do not describe the work as math, algebra, or solving "
    "equations. When verified results appear in a  block, use those exact numbers and units. "
    "Do not recompute. If no verified block is present, do not claim verification.\n\n"
    "No verified block is present, so I compute and check the result myself.\n\n"
    "**Given**\n$d = 29\\ \\text{km}$"
)


def test_instructions_copied_from_the_prompt_come_off() -> None:
    out = drop_prompt_leaks(_ECHO, "How far is the city?", instructions=_PHYSICS_RULES)
    assert out == "**Given**\n$d = 29\\ \\text{km}$"


@pytest.mark.parametrize(
    "reply",
    [
        # Ordinary advice in an instruction's shape, and a saved fact said back.
        "Use the formula v = d / t to find the speed of the car here.",
        "Bini is building a recipe app called Spoon, so the tips below fit it.",
        "Do not mix the two solutions before the test tube cools down.",
    ],
)
def test_a_sentence_the_prompt_does_not_hold_stays(reply: str) -> None:
    assert drop_prompt_leaks(reply, "q", instructions=_PHYSICS_RULES) == reply


def test_the_pass_reads_only_the_fixed_rules() -> None:
    # The physics rules a model copied are caught by the pass's own rule text; a reply
    # quoting the user's recipe, to-do or a bitcoin explainer is not (review, 2026-10-30).
    from app.modules.chat.prompt_leaks import _rule_grams

    rules = _rule_grams()
    assert drop_prompt_leaks(_ECHO, "q", rules=rules) == "**Given**\n$d = 29\\ \\text{km}$"
    for reply in (
        "1. Use a heavy-based pan for the risotto.\n2. When the stock is simmering, add one "
        "ladle at a time.\n3. Never let the rice dry out.",
        "You have two things on your list. Put the bins out on Thursday night. Call the dentist.",
        "Each verified block is then added to the chain, and it links to the one before it.",
    ):
        assert drop_prompt_leaks(reply, "q", rules=rules) == reply


@pytest.mark.parametrize(
    "reply",
    [
        "How to write a recipe card:\n- Give numbered steps, one action each, in the order "
        "they are done.\n- Keep it short.",
        "Never open with a rhetorical hook. It wastes the reader's first seconds.",
    ],
)
def test_one_sentence_of_advice_like_a_rule_stays(reply: str) -> None:
    from app.modules.chat.prompt_leaks import _rule_grams

    assert drop_prompt_leaks(reply, "How do I write it?", rules=_rule_grams()) == reply
