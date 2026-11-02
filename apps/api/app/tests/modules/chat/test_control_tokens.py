"""A leaked end-of-turn token is no reply text, and a run of them ends the stream
(2026-10-30: a Grade 10 answer card ended "<|im_end|>" and 1,100 lines of "</|im_end|>")."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.modules.chat.control_tokens import (
    drop_control_tokens,
    strip_control_tokens,
    until_control_run,
)


def test_a_leaked_token_and_its_run_leave_the_reply() -> None:
    reply = (
        "**Answer**\n\n```answer\n$t = 2 \\times 10^{-8}\\ \\text{s}$<|im_end|>\n```\n\n"
        + "</|im_end|> \n" * 40
    )
    assert strip_control_tokens(reply) == (
        "**Answer**\n\n```answer\n$t = 2 \\times 10^{-8}\\ \\text{s}$\n```\n"
    )


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        # A token the reply ends on.
        ("The answer is 4.<|endoftext|>", "The answer is 4."),
        ("Done.<|eot_id|>", "Done."),
        ("Done.<\uff5cend\u2581of\u2581sentence\uff5c>", "Done."),
        # A run of one token mid-reply.
        (
            "Part (a) is 3 A.<|im_end|>\n<|im_end|>\n<|im_end|>\n\n\nPart (b) is 6 V.",
            "Part (a) is 3 A.\n\nPart (b) is 6 V.",
        ),
    ],
)
def test_a_leak_loses_its_tokens(reply: str, kept: str) -> None:
    assert strip_control_tokens(reply) == kept


@pytest.mark.parametrize(
    "reply",
    [
        # Someone asking about the tokens gets them quoted, in code or in prose.
        "In ChatML each turn ends with `<|im_end|>`.\n",
        "Each turn ends with ``<|im_end|>``.\n",
        '```python\nprint("<|im_end|>")\n```\n',
        "```\n<|im_start|>system\nYou are helpful.<|im_end|>\n<|im_start|>user\nHi<|im_end|>\n```\n",
        "```text\n<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n```\n",
        "The **<|endoftext|>** token marks the end of a document in GPT-2's data.",
        # Not a token: a vertical bar beside angle brackets in prose or a table.
        "a <| b |> c and x|>y",
        "| a | b |\n|---|---|\n| <1 | >2 |\n",
    ],
)
def test_quoted_tokens_and_look_alikes_stay(reply: str) -> None:
    assert strip_control_tokens(reply) == reply


_SHARES = "Allocate a profit of Birr 21,400 in the ratio 1/3 : 2/5 : 2/7."


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        # 2026-10-31, Grade 11: the answer, then a turn end, then the model's own notes.
        (
            "The partners receive **Birr 7,009.35** and **Birr 8,401.87**. </|assistant|> "
            "(Don't include the corruption artifact)\n el if (rounded amounts) total? compute "
            "sum rounded: 7009.35+8401.87=15411.22",
            "The partners receive **Birr 7,009.35** and **Birr 8,401.87**.",
        ),
        (
            "Each gets 7,000 Birr.<|im_end|>\n<|im_start|>assistant\nWait, recheck.",
            "Each gets 7,000 Birr.",
        ),
        # A token mid-prose that ends nothing still goes.
        ("Shares: <|im_start|>7,000 and 8,400.", "Shares: 7,000 and 8,400."),
        # A token closing a card is stripped, the card kept.
        ("```answer\n7000<|im_end|>\n```\nDone.", "```answer\n7000\n```\nDone."),
        # Quoted code keeps its tokens even here.
        ("Use `<|im_end|>` here.\n", "Use `<|im_end|>` here.\n"),
    ],
)
def test_unasked_tokens_end_the_reply_at_a_turn_end(reply: str, kept: str) -> None:
    assert strip_control_tokens(reply, _SHARES) == kept


@pytest.mark.parametrize(
    "asked",
    [
        "What does <|im_end|> mean in ChatML?",
        "Explain the special tokens in a chat template",
        "how does the tokenizer mark the end of a document",
    ],
)
def test_a_reply_about_tokens_keeps_them_in_prose(asked: str) -> None:
    reply = "The **<|endoftext|>** token marks the end of a document. Then training goes on."
    assert strip_control_tokens(reply, asked) == reply


async def _stream(tokens: list[str]) -> AsyncIterator[str]:
    for token in tokens:
        yield token


async def test_a_run_of_one_token_ends_the_stream() -> None:
    tokens = ["The time is ", "2e-8 s.", "<|im_end|>", "\n</|", "im_end|> \n", "</|im_end|>"]
    tokens += ["\n</|im_end|>"] * 100
    stream = _Counted(tokens)
    seen = [token async for token in until_control_run(stream)]
    # The third of one token is a run: two show, and the saved reply drops them.
    assert "".join(seen) == "The time is 2e-8 s.<|im_end|>\n</|im_end|> \n</|im_end|>"
    # Nothing past the run is read: the caller closes the provider, which waited on a
    # runaway generation to the stream's cap before (2026-11-01).
    assert stream.read == 7


async def test_tokens_in_code_or_alternating_do_not_stop_the_stream() -> None:
    tokens = [
        "```\n<|im_start|>system\n",
        "Hi<|im_end|>\n<|im_end|>\n<|im_end|>\n",
        "```\n",
        "Each turn: <|im_start|>user …<|im_end|> <|im_start|>assistant …",
    ]
    seen = [token async for token in until_control_run(_stream(tokens))]
    assert seen == tokens


class _Counted:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = list(tokens)
        self.read = 0

    def __aiter__(self) -> _Counted:
        return self

    async def __anext__(self) -> str:
        if not self._tokens:
            raise StopAsyncIteration
        self.read += 1
        return self._tokens.pop(0)


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        # A turn end before any reply opens it: it goes, the reply stays (2026-11-01).
        ("</|assistant|>\nThe answer is 4.", "The answer is 4."),
        ("<|im_end|>\n\n2 + 2 = 4.", "2 + 2 = 4."),
        ("<|assistant|>Hello! How can I help?", "Hello! How can I help?"),
        # Another speaker's turn begins: the reply ends there.
        ("Hello!<|user|>What's the weather?<|assistant|>Sunny", "Hello!"),
        ("Done.<|im_start|>user\nthanks", "Done."),
        ("Done.<|start_header_id|>user<|end_header_id|>\nmore", "Done."),
        ("Paris.<|system|>You are a helpful assistant.", "Paris."),
        # The assistant's own role mid-prose ends nothing.
        ("Shares: <|im_start|>7,000 and 8,400.", "Shares: 7,000 and 8,400."),
    ],
)
def test_a_turn_end_cuts_only_after_some_reply(reply: str, kept: str) -> None:
    assert strip_control_tokens(reply, "What is 2+2?") == kept


def test_a_question_about_role_tokens_keeps_them() -> None:
    reply = "The <|user|> token marks where a user's turn begins."
    assert strip_control_tokens(reply, "What is <|user|> in a chat template?") == reply


def test_the_closed_strip_drops_every_token() -> None:
    assert drop_control_tokens("4 <|im_end|>\n```\n<|user|>\n```") == "4 \n```\n\n```"


@pytest.mark.parametrize(
    "tokens",
    [
        # A run quoted in `inline` code, whole or still streaming its closing backtick.
        ["Use `", "<|a_b|><|a_b|><|a_b|>", "` to test the template."],
        ["Use ``", "<|a_b|>", "<|a_b|>", "<|a_b|>", "`` here."],
    ],
)
async def test_a_run_in_inline_code_is_text(tokens: list[str]) -> None:
    seen = [token async for token in until_control_run(_stream(tokens))]
    assert seen == tokens


async def test_a_run_after_closed_inline_code_still_ends_the_stream() -> None:
    tokens = ["See `x` then ", "<|im_end|>", "<|im_end|>", "<|im_end|>", " more"]
    seen = [token async for token in until_control_run(_stream(tokens))]
    assert "".join(seen) == "See `x` then <|im_end|><|im_end|>"


@pytest.mark.parametrize(
    ("opening", "most"),
    [
        # Review of #2194: a closing fence's backticks and a stray backtick open no span,
        # and the guard read a runaway on the same line to the stream's cap.
        ("```python\nprint(1)\n```", 4),
        ("Press the ` key", 40),
    ],
)
async def test_a_run_after_a_fence_or_a_stray_backtick_ends_the_stream(
    opening: str, most: int
) -> None:
    stream = _Counted([opening] + ["<|im_end|>"] * 5000)
    seen = [token async for token in until_control_run(stream)]
    assert seen[0] == opening
    assert stream.read <= most
